/**
 * Application state for one week.
 *
 * The whole week is fetched in a single request and then held in memory.
 * Mutations return the updated resource, so state is patched from the
 * response rather than triggering a refetch. That is what makes clicking
 * around feel instant: the network is touched when data actually changes,
 * not on every interaction.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { AppState, GroceryLine, Meal } from "../api/types";
import { mondayOf } from "../lib/dates";

export function usePlanner() {
  const [week, setWeek] = useState(() => mondayOf(new Date()));
  const [state, setState] = useState<AppState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [grocery, setGrocery] = useState<GroceryLine[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setGrocery(null);

    api
      .getState(week)
      .then((next) => {
        // A slower earlier request must not overwrite a newer week.
        if (!cancelled) {
          setState(next);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(describe(err)))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [week]);

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
          setGrocery(null);
        }
      }),

    copyPreviousWeek: () =>
      mutate(() => api.copyPreviousWeek(week)).then((plan) => {
        if (plan) {
          setState((current) =>
            current ? { ...current, plan: plan.days } : current,
          );
          setGrocery(null);
        }
      }),

    generateGroceryList: () =>
      mutate(() => api.getGroceryList(week)).then(
        (lines) => lines && setGrocery(lines),
      ),
  };

  return {
    week,
    setWeek,
    state,
    loading,
    error,
    busy,
    grocery,
    dismissError: () => setError(null),
    ...actions,
  };
}

function describe(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
