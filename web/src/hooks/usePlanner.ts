/**
 * Application state for one week, held in the TanStack Query cache.
 *
 * Three kinds of server state, each with its own cache entry:
 *
 * - the library (meals, ingredient suggestions, templates), which does not vary by
 *   week;
 * - one plan per week visited;
 * - one grocery list per week, fetched by the pages that show it.
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
  IngredientLine,
  IngredientSuggestion,
  Meal,
  WeekPlan,
} from "../api/types";
import { parseWeek, useSearchParam } from "../lib/location";

type Library = Pick<AppState, "meals" | "ingredient_suggestions" | "templates">;

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
  const grocery = useQuery({
    queryKey: queryKeys.grocery(week),
    queryFn: () => api.getGroceryList(week),
    enabled: loadGroceries && library.isSuccess,
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
    addMeal: (name: string, servings: number) =>
      runFor(mealChange.mutateAsync(() => api.createMeal(name, servings))),

    addFromTemplate: (templateName: string) =>
      runFor(mealChange.mutateAsync(() => api.createMealFromTemplate(templateName))),

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

    replaceIngredients: (mealId: number, ingredients: IngredientLine[]) =>
      runFor(mealChange.mutateAsync(() => api.replaceIngredients(mealId, ingredients))),

    // The week is named by the caller, not read from the URL at send time:
    // a save made just before changing week must still land on its own week.
    // Both resolve with the saved plan, or null if it failed.
    savePlan: (weekStart: string, days: AppState["plan"]) =>
      runFor(planChange.mutateAsync(() => api.setPlan(weekStart, days))),

    copyPreviousWeek: (weekStart: string) =>
      runFor(planChange.mutateAsync(() => api.copyPreviousWeek(weekStart))),

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
    mealsPending: mealChange.isPending || mealDeletion.isPending || reading.isPending,
    planPending: planChange.isPending,
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
