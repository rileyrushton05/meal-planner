/**
 * The API's types, under the names the app uses.
 *
 * Every type here is generated: `schema.ts` is produced from the committed
 * OpenAPI document (docs/openapi.json), which is exported from the Pydantic
 * models. After changing a model or route:
 *
 *     python scripts/export_openapi.py      (repo root)
 *     npm run generate:api                  (web/)
 *
 * CI fails if either file is stale, so a renamed field or a changed
 * nullability breaks the build instead of surfacing as `undefined`.
 */

import { type components, dayOfWeekValues } from "./schema";

type Schemas = components["schemas"];

/** The seven days, Monday first, exactly as the API's enum declares them. */
export type Day = Schemas["DayOfWeek"];
export const DAYS: readonly Day[] = dayOfWeekValues;

export type IngredientAmount = Schemas["IngredientAmount"];
export type Meal = Schemas["MealRead"];
export type DayAssignment = Schemas["DayAssignment"];
export type DayAssignmentWrite = Schemas["DayAssignmentWrite"];
export type GroceryLine = Schemas["GroceryLine"];
export type TemplateIngredient = Schemas["TemplateIngredientRead"];
export type MealTemplate = Schemas["TemplateRead"];
/** Everything needed to render one week, fetched in a single request. */
export type AppState = Schemas["AppState"];
export type WeekPlan = Schemas["WeekPlanRead"];
/** Who is signed in: a guest (no email) or an account. */
export type Account = Schemas["Account"];
/** A download of everything that is the caller's own. */
export type AccountExport = Schemas["AccountExport"];
/** The body of every error response (RFC 9457). */
export type Problem = Schemas["Problem"];
