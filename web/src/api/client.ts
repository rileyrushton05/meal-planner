/**
 * Typed wrapper over the HTTP API.
 *
 * Every call goes through `request`, so error handling and JSON decoding
 * live in one place. Paths are relative: in development Vite proxies /api to
 * the local server, and in production Vercel serves both from one origin.
 */

import { mondayOf } from "../lib/dates";
import type {
  Account,
  AccountExport,
  RecoveryCode,
  SignedUp,
  AppState,
  DayAssignmentWrite,
  GroceryLine,
  Meal,
  Problem,
  WeekPlan,
} from "./types";

/**
 * An error carrying the message the API wrote for the user.
 *
 * Every API error is an RFC 9457 problem: `detail` becomes the message,
 * `type` identifies the kind of failure for code that needs to branch on it,
 * and `requestId` matches the server's log lines for that request.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly type: string | null;
  readonly requestId: string | null;

  constructor(
    status: number,
    message: string,
    { type = null, requestId = null }: { type?: string | null; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.type = type;
    this.requestId = requestId;
  }
}

const NOT_SIGNED_IN = "urn:meal-planner:problem:not-signed-in";

let guestSession: Promise<void> | null = null;
const guestSessionListeners = new Set<() => void>();

/**
 * Be told whenever a guest session has been started because a request found
 * itself signed out. On a first visit that is expected; mid-session it means
 * the old session ended, and anything cached belonged to it.
 * Returns a function that stops listening.
 */
export function onGuestSessionStarted(listener: () => void): () => void {
  guestSessionListeners.add(listener);
  return () => guestSessionListeners.delete(listener);
}

/**
 * Start a guest session: a real account with no email or password, so a
 * first visit lands in a working planner instead of a sign-in wall, with
 * sample meals planned in this week (the browser's week, since the server
 * cannot know the visitor's time zone).
 *
 * Shared by every request that finds itself signed out at the same moment,
 * so a page load firing several requests starts one session, not one each.
 * A request arriving just after it finishes already carries the new cookie,
 * and the server answers that with the same account rather than another.
 */
function startGuestSession(): Promise<void> {
  guestSession ??= fetch("/api/auth/guest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_week: mondayOf(new Date()) }),
  })
    .then(async (response) => {
      if (!response.ok) throw await toApiError(response);
      for (const listener of guestSessionListeners) listener();
    })
    .finally(() => {
      guestSession = null;
    });
  return guestSession;
}

const SAFE_METHODS = new Set(["GET", "HEAD"]);
/** Signing in and out decide the session themselves; a 401 from one of
 *  these is an answer, not a reason to start a guest session. */
const SESSION_ROUTES = new Set([
  "/api/auth/guest",
  "/api/auth/signup",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/recover",
]);

async function request<T>(
  path: string,
  init?: RequestInit,
  { retried = false }: { retried?: boolean } = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const error = await toApiError(response);
    // Signed out (first visit, or a session that ended): start a guest
    // session. Never for the routes that sign in and out, and never twice,
    // so a server that keeps refusing cannot cause a loop.
    if (error.type === NOT_SIGNED_IN && !retried && !SESSION_ROUTES.has(path)) {
      await startGuestSession();
      // A read is simply asked again. A change is not: it was meant for
      // the account whose session ended, and replaying it would quietly
      // save it into a brand-new guest account instead.
      if (SAFE_METHODS.has((init?.method ?? "GET").toUpperCase())) {
        return request<T>(path, init, { retried: true });
      }
      throw new ApiError(
        401,
        "Your session had ended, so that change wasn't saved. " +
          "You're now in a new guest session; log in to get back to your account.",
        { type: NOT_SIGNED_IN, requestId: error.requestId },
      );
    }
    throw error;
  }

  // 204 No Content has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Build an ApiError from a failed response.
 *
 * The API writes `detail` as a sentence for the user, so it is shown as is.
 * Anything else in that field was written for developers and is replaced
 * with a generic message rather than leaking a field path into the UI.
 */
async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers?.get("X-Request-ID") ?? null;
  // Kept even when there is no usable detail: code branches on the type
  // (a 401 that means "not signed in"), whatever the message says.
  let type: string | null = null;
  try {
    const body: Partial<Problem> | undefined = await response.json();
    type = typeof body?.type === "string" ? body.type : null;
    if (typeof body?.detail === "string") {
      return new ApiError(response.status, body.detail, { type, requestId });
    }
    if (body?.detail !== undefined) {
      return new ApiError(
        response.status,
        "That doesn't look right — please check the values and try again.",
        { type, requestId },
      );
    }
  } catch {
    // Body was not JSON; fall through to the status-based message.
  }
  return new ApiError(response.status, `Request failed (${response.status}).`, {
    type,
    requestId,
  });
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

  setPlan: (week: string, days: DayAssignmentWrite[]): Promise<WeekPlan> =>
    request(`/api/plan/${week}`, {
      method: "PUT",
      body: JSON.stringify({ days }),
    }),

  copyPreviousWeek: (week: string): Promise<WeekPlan> =>
    request(`/api/plan/${week}/copy-previous`, { method: "POST" }),

  getGroceryList: (week: string): Promise<GroceryLine[]> =>
    request(`/api/grocery-list/${week}`),

  /** Who is signed in. Signed out, this starts a guest session first. */
  me: (): Promise<Account> => request("/api/auth/me"),

  /** Create an account; a guest becomes it, keeping their meals. The
   *  response carries the account's recovery code, to show once. */
  signUp: (email: string, password: string): Promise<SignedUp> =>
    request("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logIn: (email: string, password: string): Promise<Account> =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logOut: (): Promise<void> => request("/api/auth/logout", { method: "POST" }),

  /** A forgotten password replaced using the recovery code; signs in, and
   *  carries the next recovery code (each works once). */
  recover: (email: string, recoveryCode: string, newPassword: string): Promise<SignedUp> =>
    request("/api/auth/recover", {
      method: "POST",
      body: JSON.stringify({
        email,
        recovery_code: recoveryCode,
        new_password: newPassword,
      }),
    }),

  /** A new recovery code, confirmed with the password; the old one stops. */
  replaceRecoveryCode: (password: string): Promise<RecoveryCode> =>
    request("/api/account/recovery-code", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  /** Everything that is the caller's own, for them to keep. */
  exportAccount: (): Promise<AccountExport> => request("/api/account/export"),

  /** Delete the account and all of it, for good. An account confirms with
   *  its password; a guest has none to give. */
  deleteAccount: (password?: string): Promise<void> =>
    request("/api/account", {
      method: "DELETE",
      body: JSON.stringify(password === undefined ? {} : { password }),
    }),
};
