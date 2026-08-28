/**
 * Typed wrapper over the HTTP API.
 *
 * Every call goes through `request`, so error handling and JSON decoding
 * live in one place. Paths are relative: in development Vite proxies /api to
 * the local server, and in production Vercel serves both from one origin.
 */

import type { AppState, GroceryLine, Meal, WeekPlan } from "./types";

/** An error carrying the message the API wrote for the user. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  // 204 No Content has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Pull a human-readable message out of a failed response.
 *
 * Domain errors return {detail: "..."} written for the user. Validation
 * errors return FastAPI's array form, which is not, so those get a generic
 * message rather than leaking a field path into the UI.
 */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body?.detail)) {
      return "That doesn't look right — please check the values and try again.";
    }
  } catch {
    // Body was not JSON; fall through to the status-based message.
  }
  return `Request failed (${response.status}).`;
}

export const api = {
  /** Everything needed to render a week, in one round trip. */
  getState: (week: string): Promise<AppState> =>
    request(`/api/state?week=${week}`),

  /** Just the day assignments. Meals and templates do not vary by week, so
   *  changing week fetches this rather than the whole of getState. */
  getPlan: (week: string): Promise<WeekPlan> => request(`/api/plan/${week}`),

  createMeal: (name: string, servings: number): Promise<Meal> =>
    request("/api/meals", {
      method: "POST",
      body: JSON.stringify({ name, servings }),
    }),

  createMealFromTemplate: (templateName: string): Promise<Meal> =>
    request(`/api/meals/from-template/${encodeURIComponent(templateName)}`, {
      method: "POST",
    }),

  updateMeal: (id: number, name: string, servings: number): Promise<Meal> =>
    request(`/api/meals/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name, servings }),
    }),

  deleteMeal: (id: number): Promise<void> =>
    request(`/api/meals/${id}`, { method: "DELETE" }),

  addIngredient: (
    mealId: number,
    name: string,
    qty: number,
    unit: string,
  ): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients`, {
      method: "POST",
      body: JSON.stringify({ name, qty, unit }),
    }),

  updateIngredient: (
    mealId: number,
    ingredientId: number,
    qty: number,
    unit: string,
  ): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients/${ingredientId}`, {
      method: "PATCH",
      body: JSON.stringify({ qty, unit }),
    }),

  removeIngredient: (mealId: number, ingredientId: number): Promise<Meal> =>
    request(`/api/meals/${mealId}/ingredients/${ingredientId}`, {
      method: "DELETE",
    }),

  setPlan: (
    week: string,
    days: { day: string; meal_id: number | null; servings: number | null }[],
  ): Promise<WeekPlan> =>
    request(`/api/plan/${week}`, {
      method: "PUT",
      body: JSON.stringify({ days }),
    }),

  copyPreviousWeek: (week: string): Promise<WeekPlan> =>
    request(`/api/plan/${week}/copy-previous`, { method: "POST" }),

  getGroceryList: (week: string): Promise<GroceryLine[]> =>
    request(`/api/grocery-list/${week}`),
};
