/**
 * Application state for one week.
 *
 * The first load fetches everything in a single request and then holds it in
 * memory. Mutations return the updated resource, so state is patched from the
 * response rather than triggering a refetch. That is what makes clicking
 * around feel instant: the network is touched when data actually changes,
 * not on every interaction.
 *
 * Changing week is the one exception, and it fetches only the day
 * assignments - meals, templates and ingredient names do not vary by week, so
 * refetching them cost three extra queries per arrow click. Weeks already
 * seen are served from `seenWeeks` and cost nothing at all.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { AppState, GroceryLine, Meal } from "../api/types";
import { mondayOf } from "../lib/dates";

export function usePlanner() {
  const [week, setWeek] = useState(() => mondayOf(new Date()));
  const [state, setState] = useState<AppState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Tagged with the week it was generated for. Deriving visibility from that
  // is what lets the week-change effect avoid a setState purely to clear it,
  // and means returning to a week shows the list you already generated.
  const [grocery, setGrocery] = useState<{
    week: string;
    lines: GroceryLine[];
  } | null>(null);

  // Day assignments for weeks already fetched, so going back to one is free.
  // A ref rather than state: reading it must not itself trigger a render.
  const seenWeeks = useRef(new Map<string, AppState["plan"]>());
  // Whether the one-off bootstrap has happened. A ref, not `state`, so this
  // effect depends only on `week` - depending on `state` would refetch on
  // every mutation.
  const bootstrapped = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const cached = seenWeeks.current.get(week);
    if (cached) {
      // week_start moves too, or the heading keeps naming the week we left.
      setState((current) =>
        current ? { ...current, week_start: week, plan: cached } : current,
      );
      return;
    }

    setLoading(true);
    // Only the very first load needs the meals, templates and ingredient
    // names; after that a week change is just its plan.
    const load = bootstrapped.current
      ? api.getPlan(week).then((p) => ({ start: p.week_start, plan: p.days }))
      : api.getState(week).then((next) => ({ full: next }));

    load
      .then((result) => {
        // A slower earlier request must not overwrite a newer week.
        if (cancelled) return;
        if ("full" in result) {
          bootstrapped.current = true;
          setState(result.full);
          seenWeeks.current.set(result.full.week_start, result.full.plan);
        } else {
          setState((current) =>
            current
              ? { ...current, week_start: result.start, plan: result.plan }
              : current,
          );
          seenWeeks.current.set(result.start, result.plan);
        }
        setError(null);
      })
      .catch((err) => !cancelled && setError(describe(err)))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [week]);

  /** Record a plan we just wrote, so returning to this week shows it. */
  const rememberPlan = useCallback(
    (weekStart: string, plan: AppState["plan"]) => {
      seenWeeks.current.set(weekStart, plan);
    },
    [],
  );

  /** Drop every cached week, after a change that can affect all of them. */
  const forgetWeeks = useCallback(() => seenWeeks.current.clear(), []);

  /** Run a mutation, surface any error, and keep the UI responsive. */
  const mutate = useCallback(async <T,>(action: () => Promise<T>) => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(describe(err));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  /** Replace one meal in place, or append it if it is new. */
  const upsertMeal = useCallback((meal: Meal) => {
    setState((current) => {
      if (!current) return current;
      const exists = current.meals.some((m) => m.id === meal.id);
      return {
        ...current,
        meals: exists
          ? current.meals.map((m) => (m.id === meal.id ? meal : m))
          : [...current.meals, meal],
        // A new ingredient may have appeared, and the picker reads this list.
        ingredient_names: Array.from(
          new Set([
            ...current.ingredient_names,
            ...meal.ingredients.map((i) => i.name),
          ]),
        ).sort(),
      };
    });
    // The grocery list is derived from meals, so it is now stale.
    setGrocery(null);
  }, []);

  const actions = {
    addMeal: (name: string, servings: number) =>
      mutate(() => api.createMeal(name, servings)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    addFromTemplate: (templateName: string) =>
      mutate(() => api.createMealFromTemplate(templateName)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    updateMeal: (id: number, name: string, servings: number) =>
      mutate(() => api.updateMeal(id, name, servings)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    deleteMeal: (id: number) =>
      mutate(() => api.deleteMeal(id)).then(() => {
        setState((current) =>
          current
            ? {
                ...current,
                meals: current.meals.filter((m) => m.id !== id),
                // Deleting a meal clears it from any day it was planned on.
                plan: current.plan.map((d) =>
                  d.meal_id === id ? { ...d, meal_id: null, servings: null } : d,
                ),
              }
            : current,
        );
        // The meal is unassigned from every week, not just this one, so no
        // cached plan can be trusted.
        forgetWeeks();
        setGrocery(null);
      }),

    addIngredient: (mealId: number, name: string, qty: number, unit: string) =>
      mutate(() => api.addIngredient(mealId, name, qty, unit)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    updateIngredient: (
      mealId: number,
      ingredientId: number,
      qty: number,
      unit: string,
    ) =>
      mutate(() => api.updateIngredient(mealId, ingredientId, qty, unit)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    removeIngredient: (mealId: number, ingredientId: number) =>
      mutate(() => api.removeIngredient(mealId, ingredientId)).then(
        (meal) => meal && upsertMeal(meal),
      ),

    savePlan: (days: AppState["plan"]) =>
      mutate(() => api.setPlan(week, days)).then((plan) => {
        if (plan) {
          setState((current) =>
            current ? { ...current, plan: plan.days } : current,
          );
          rememberPlan(week, plan.days);
          setGrocery(null);
        }
      }),

    copyPreviousWeek: () =>
      mutate(() => api.copyPreviousWeek(week)).then((plan) => {
        if (plan) {
          setState((current) =>
            current ? { ...current, plan: plan.days } : current,
          );
          rememberPlan(week, plan.days);
          setGrocery(null);
        }
      }),

    generateGroceryList: () =>
      mutate(() => api.getGroceryList(week)).then(
        (lines) => lines && setGrocery({ week, lines }),
      ),
  };

  return {
    week,
    setWeek,
    state,
    loading,
    error,
    busy,
    // Only ever the list for the week on screen.
    grocery: grocery?.week === week ? grocery.lines : null,
    dismissError: () => setError(null),
    ...actions,
  };
}

function describe(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
