/**
 * Application state for one week, held in the TanStack Query cache.
 *
 * Three kinds of server state, each with its own cache entry:
 *
 * - the library (meals, ingredient suggestions, templates), which does not vary by
 *   week;
 * - one plan per week visited;
 * - one grocery list per week, fetched by the pages that show it, with
 *   what has been ticked off, the extras, the usuals and the aisle order.
 *
 * The first load is a single request (`/api/state`) that fills the library
 * and seeds the current week's plan, so nothing else is fetched. Changing
 * week fetches only that week's plan, and a week already visited costs
 * nothing. Mutations patch the cache from the API's response instead of
 * refetching, which is what makes the app feel instant: the network is used
 * when data changes, not when it is looked at.
 *
 * The week lives in the URL (`?week=`), so a refresh or a shared link opens
 * the same week.
 */

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../api/client";
import { queryKeys } from "../api/queryClient";
import type {
  AppState,
  Category,
  CheckState,
  Day,
  GroceryList,
  GroceryUsual,
  IngredientLine,
  IngredientSuggestion,
  Meal,
  WeekPlan,
} from "../api/types";
import { parseWeek, useSearchParam } from "../lib/location";

type Library = Pick<AppState, "meals" | "ingredient_suggestions" | "templates">;
type SuggestionRequest = { weekStart: string; empty: Day[]; planned: number[] };
type CheckRequest = { weekStart: string; key: string; state: CheckState | null };

/** How often a grocery list on screen is fetched again, for ticks made on
 *  another device. Only while the page is visible (TanStack's default). */
const GROCERY_REFRESH_MS = 20_000;

export function usePlanner({
  loadGroceries = false,
}: {
  /**
   * Fetch the week's grocery list, and again whenever a change outdates it:
   * for the pages that show it (the list, and home's count of items).
   */
  loadGroceries?: boolean;
} = {}) {
  const queryClient = useQueryClient();
  const [week, setWeek] = useSearchParam("week", parseWeek);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dismissedError, setDismissedError] = useState<unknown>(null);

  const library = useQuery({
    queryKey: queryKeys.library,
    queryFn: async (): Promise<Library> => {
      const state = await api.getState(week);
      // Seeding the plan cache here is what keeps the first load to one
      // request: the plan query below is enabled only after this succeeds,
      // and finds its week already cached.
      queryClient.setQueryData<WeekPlan>(queryKeys.plan(state.week_start), {
        week_start: state.week_start,
        days: state.plan,
      });
      return {
        meals: state.meals,
        ingredient_suggestions: state.ingredient_suggestions,
        templates: state.templates,
      };
    },
  });

  const plan = useQuery({
    queryKey: queryKeys.plan(week),
    queryFn: () => api.getPlan(week),
    enabled: library.isSuccess,
    // Keep the week we are leaving on screen, dimmed, rather than blanking
    // the page while the next one loads.
    placeholderData: keepPreviousData,
  });

  // Held per week: returning to a week shows the list already fetched for
  // it. A change resets it (below): fetched again straight away on a page
  // that shows it, and otherwise when one next does.
  //
  // Unlike the rest, a list is also fetched again on its own while it is on
  // screen: its ticks are shared by everyone on the account, so two people
  // shopping, or a laptop left open on it, see each other's ticks.
  const grocery = useQuery({
    queryKey: queryKeys.grocery(week),
    queryFn: () => api.getGroceries(week),
    enabled: loadGroceries && library.isSuccess,
    refetchOnWindowFocus: "always",
    refetchInterval: GROCERY_REFRESH_MS,
  });

  const report = (err: unknown) => setActionError(describe(err));
  const clearError = () => setActionError(null);

  /** A grocery list is derived from meals and plans, so changes outdate it. */
  const forgetGroceries = (weekStart?: string) =>
    queryClient.resetQueries({
      queryKey: weekStart ? queryKeys.grocery(weekStart) : queryKeys.groceries,
    });

  /** Replace one meal in the library, or append it if it is new. */
  const upsertMeal = (meal: Meal) => {
    queryClient.setQueryData<Library>(queryKeys.library, (current) =>
      current
        ? {
            ...current,
            meals: current.meals.some((m) => m.id === meal.id)
              ? current.meals.map((m) => (m.id === meal.id ? meal : m))
              : [...current.meals, meal],
            // A new ingredient may have appeared, and the picker reads this.
            ingredient_suggestions: withNewIngredients(
              current.ingredient_suggestions,
              meal,
            ),
          }
        : current,
    );
    forgetGroceries();
  };

  const mealChange = useMutation({
    mutationFn: (change: () => Promise<Meal>) => change(),
    onMutate: clearError,
    onSuccess: upsertMeal,
    onError: report,
  });

  const mealDeletion = useMutation({
    mutationFn: async (id: number) => {
      await api.deleteMeal(id);
      return id;
    },
    onMutate: clearError,
    onSuccess: (id) => {
      queryClient.setQueryData<Library>(queryKeys.library, (current) =>
        current
          ? { ...current, meals: current.meals.filter((m) => m.id !== id) }
          : current,
      );
      // The server unassigns the meal from every day of every week, so do
      // the same to every week in the cache rather than refetching them.
      queryClient.setQueriesData<WeekPlan>({ queryKey: queryKeys.plans }, (p) =>
        p
          ? {
              ...p,
              days: p.days.map((d) =>
                d.meal_id === id ? { ...d, meal_id: null, servings: null } : d,
              ),
            }
          : p,
      );
      forgetGroceries();
    },
    onError: report,
  });

  const reading = useMutation({
    mutationFn: (text: string) => api.parseIngredients(text),
    onMutate: clearError,
    onError: report,
  });

  const importing = useMutation({
    mutationFn: (url: string) => api.importRecipe(url),
    onMutate: clearError,
    onError: report,
  });

  const suggesting = useMutation({
    mutationFn: ({ weekStart, empty, planned }: SuggestionRequest) =>
      api.suggestMeals(weekStart, empty, planned),
    onMutate: clearError,
    onError: report,
  });

  /** A list the server sent back, filed under the week it says it is. */
  const storeGroceries = (list: GroceryList) =>
    queryClient.setQueryData(queryKeys.grocery(list.week_start), list);

  /** The same change to every week's cached list: usuals and the aisle
   *  order are the person's, not one week's. */
  const patchEveryList = (patch: (list: GroceryList) => GroceryList) =>
    queryClient.setQueriesData<GroceryList>({ queryKey: queryKeys.groceries }, (list) =>
      list ? patch(list) : list,
    );

  const groceryChange = useMutation({
    mutationFn: (change: () => Promise<GroceryList>) => change(),
    onMutate: clearError,
    onSuccess: storeGroceries,
    onError: report,
  });

  const usualsChange = useMutation({
    mutationFn: (change: () => Promise<GroceryUsual[]>) => change(),
    onMutate: clearError,
    onSuccess: (usuals) => patchEveryList((list) => ({ ...list, usuals })),
    onError: report,
  });

  // Saved behind the tick, which `setGroceryCheck` has already shown. The
  // server answers with nothing, so once the last tick in flight has landed
  // the list is fetched again: that puts right a tick that failed, and a
  // refresh that crossed with one, and shows ticks from other devices.
  const checking = useMutation({
    mutationKey: ["grocery-check"],
    mutationFn: ({ weekStart, key, state }: CheckRequest) =>
      api.setGroceryCheck(weekStart, key, state),
    onMutate: clearError,
    onError: report,
    onSettled: (_data, _error, { weekStart }) => {
      if (queryClient.isMutating({ mutationKey: ["grocery-check"] }) === 1) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.grocery(weekStart) });
      }
    },
  });

  const ordering = useMutation({
    mutationFn: (order: Category[]) => api.setAisleOrder(order),
    onMutate: (order) => {
      clearError();
      const before = queryClient.getQueriesData<GroceryList>({ queryKey: queryKeys.groceries });
      patchEveryList((list) => ({ ...list, aisle_order: order }));
      return { before };
    },
    onSuccess: (order) => patchEveryList((list) => ({ ...list, aisle_order: order })),
    onError: (err, _order, context) => {
      for (const [key, list] of context?.before ?? []) queryClient.setQueryData(key, list);
      report(err);
    },
  });

  const planChange = useMutation({
    mutationFn: (change: () => Promise<WeekPlan>) => change(),
    onMutate: clearError,
    // Keyed by the week the server says it saved, not the week on screen,
    // so switching week mid-request cannot file the plan under the wrong one.
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.plan(saved.week_start), saved);
      forgetGroceries(saved.week_start);
    },
    onError: report,
  });

  /** Run a mutation; failures are reported through `error`, not thrown. */
  const run = <T,>(promise: Promise<T>): Promise<void> =>
    promise.then(
      () => undefined,
      () => undefined,
    );

  /** As `run`, but resolving with the result, or null if it failed. */
  const runFor = <T,>(promise: Promise<T>): Promise<T | null> =>
    promise.catch(() => null);

  const actions = {
    // Resolve with the new meal, so the page can open it straight away.
    addMeal: (name: string, servings: number, ingredients: IngredientLine[] = []) =>
      runFor(mealChange.mutateAsync(() => api.createMeal(name, servings, ingredients))),

    addFromTemplate: (templateName: string) =>
      runFor(mealChange.mutateAsync(() => api.createMealFromTemplate(templateName))),

    duplicateMeal: (id: number) =>
      runFor(mealChange.mutateAsync(() => api.duplicateMeal(id))),

    updateMeal: (id: number, name: string, servings: number) =>
      run(mealChange.mutateAsync(() => api.updateMeal(id, name, servings))),

    deleteMeal: (id: number) => run(mealDeletion.mutateAsync(id)),

    addIngredient: (mealId: number, name: string, qty: number, unit: string) =>
      run(mealChange.mutateAsync(() => api.addIngredient(mealId, name, qty, unit))),

    updateIngredient: (
      mealId: number,
      ingredientId: number,
      qty: number,
      unit: string,
    ) =>
      run(
        mealChange.mutateAsync(() =>
          api.updateIngredient(mealId, ingredientId, qty, unit),
        ),
      ),

    removeIngredient: (mealId: number, ingredientId: number) =>
      run(mealChange.mutateAsync(() => api.removeIngredient(mealId, ingredientId))),

    // Both resolve with the result, or null if it failed.
    readIngredients: (text: string) => runFor(reading.mutateAsync(text)),

    importRecipe: (url: string) => runFor(importing.mutateAsync(url)),

    replaceIngredients: (mealId: number, ingredients: IngredientLine[]) =>
      runFor(mealChange.mutateAsync(() => api.replaceIngredients(mealId, ingredients))),

    // The week is named by the caller, not read from the URL at send time:
    // a save made just before changing week must still land on its own week.
    // Both resolve with the saved plan, or null if it failed.
    savePlan: (weekStart: string, days: AppState["plan"]) =>
      runFor(planChange.mutateAsync(() => api.setPlan(weekStart, days))),

    copyPreviousWeek: (weekStart: string) =>
      runFor(planChange.mutateAsync(() => api.copyPreviousWeek(weekStart))),

    /** Meals for the empty days, or null if that failed. Saves nothing:
     *  the plan page applies them, as a change it saves and can undo. */
    suggestMeals: (weekStart: string, empty: Day[], planned: number[]) =>
      runFor(suggesting.mutateAsync({ weekStart, empty, planned })),

    // The grocery list. Each takes the week it is for, as `savePlan` does.
    // Shown before anything is sent, and synchronously: inside the click,
    // so the checkbox never flicks back while the list catches up, and a
    // tick in the shop never waits for the network.
    setGroceryCheck: (weekStart: string, key: string, state: CheckState | null) => {
      queryClient.setQueryData<GroceryList>(queryKeys.grocery(weekStart), (list) =>
        list
          ? {
              ...list,
              lines: list.lines.map((line) => (line.key === key ? { ...line, state } : line)),
            }
          : list,
      );
      return run(checking.mutateAsync({ weekStart, key, state }));
    },

    emptyBasket: (weekStart: string) =>
      run(groceryChange.mutateAsync(() => api.emptyBasket(weekStart))),

    /** Resolves true once added, so the field can be cleared; false keeps
     *  what was typed, to fix. */
    addExtra: (weekStart: string, text: string) =>
      runFor(groceryChange.mutateAsync(() => api.addExtra(weekStart, text))).then(Boolean),

    removeExtra: (weekStart: string, extraId: number) =>
      run(groceryChange.mutateAsync(() => api.removeExtra(weekStart, extraId))),

    keepExtra: (weekStart: string, extraId: number) =>
      run(groceryChange.mutateAsync(() => api.keepExtra(weekStart, extraId))),

    addUsuals: (weekStart: string) =>
      run(groceryChange.mutateAsync(() => api.addUsuals(weekStart))),

    addUsual: (text: string) =>
      runFor(usualsChange.mutateAsync(() => api.addUsual(text))).then(Boolean),

    removeUsual: (id: number) => run(usualsChange.mutateAsync(() => api.removeUsual(id))),

    setAisleOrder: (order: Category[]) => run(ordering.mutateAsync(order)),

  };

  const state: AppState | null =
    library.data && plan.data
      ? { ...library.data, week_start: plan.data.week_start, plan: plan.data.days }
      : null;

  // A failed load stays visible until dismissed; a failed action replaces it.
  const loadError = library.error ?? plan.error ?? grocery.error;
  const error =
    actionError ??
    (loadError && loadError !== dismissedError ? describe(loadError) : null);

  return {
    week,
    setWeek,
    state,
    loading: !state || plan.isPlaceholderData,
    error,
    dismissError: () => {
      setActionError(null);
      setDismissedError(loadError);
    },
    // Pending work per area, so one slow save does not freeze the whole app.
    mealsPending:
      mealChange.isPending ||
      mealDeletion.isPending ||
      reading.isPending ||
      importing.isPending,
    planPending: planChange.isPending || suggesting.isPending,
    // Ticks are left out: each shows at once, so there is nothing to wait for.
    groceryPending: groceryChange.isPending || usualsChange.isPending || ordering.isPending,
    grocery: grocery.data ?? null,
    ...actions,
  };
}

/**
 * The suggestions with any ingredient of `meal` they lack, offered in the
 * unit it was just used in. Sorted as the server sorts them.
 */
function withNewIngredients(
  suggestions: IngredientSuggestion[],
  meal: Meal,
): IngredientSuggestion[] {
  const known = new Set(suggestions.map((s) => s.name.toLowerCase()));
  const added = meal.ingredients
    .filter((i) => !known.has(i.name.toLowerCase()))
    .map((i) => ({ name: i.name, unit: i.unit }));
  if (added.length === 0) return suggestions;
  return [...suggestions, ...added].sort((a, b) =>
    a.name.toLowerCase().localeCompare(b.name.toLowerCase()),
  );
}

function describe(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
