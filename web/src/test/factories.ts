/** Builders for API payloads, so tests state only what they care about. */

import type { AppState, Meal, MealTemplate } from "../api/types";

export function makeMeal(overrides: Partial<Meal> = {}): Meal {
  return {
    id: 1,
    name: "Spaghetti",
    servings: 4,
    ingredients: [],
    ...overrides,
  };
}

export function makeTemplate(overrides: Partial<MealTemplate> = {}): MealTemplate {
  return {
    name: "Omelette",
    servings: 1,
    ingredients: [{ name: "Eggs", qty: 3, unit: "" }],
    ...overrides,
  };
}

export function makeState(overrides: Partial<AppState> = {}): AppState {
  return {
    week_start: "2026-08-03",
    meals: [],
    ingredient_names: [],
    plan: [],
    templates: [],
    ...overrides,
  };
}
