/**
 * Types mirroring the Pydantic schemas in server/schemas.py.
 *
 * Hand-written rather than generated so the frontend stays readable, but
 * they are checked against the live API by a test, so drift fails the build
 * rather than surfacing as undefined at runtime.
 */

export const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

export type Day = (typeof DAYS)[number];

export interface IngredientAmount {
  ingredient_id: number;
  name: string;
  qty: number;
  unit: string;
}

export interface Meal {
  id: number;
  name: string;
  servings: number;
  ingredients: IngredientAmount[];
}

export interface DayAssignment {
  /** The union, not `string`: the API rejects anything else with a 422, so
   *  accepting a wider type here would only hide mistakes until runtime. */
  day: Day;
  meal_id: number | null;
  servings: number | null;
}

export interface GroceryLine {
  name: string;
  qty: number;
  unit: string;
  /** Preformatted for display, e.g. "400 g" or "2". */
  display: string;
}

export interface TemplateIngredient {
  name: string;
  qty: number;
  unit: string;
}

export interface MealTemplate {
  name: string;
  servings: number;
  ingredients: TemplateIngredient[];
}

/** Everything needed to render one week, fetched in a single request. */
export interface AppState {
  week_start: string;
  meals: Meal[];
  ingredient_names: string[];
  plan: DayAssignment[];
  templates: MealTemplate[];
}

export interface WeekPlan {
  week_start: string;
  days: DayAssignment[];
}
