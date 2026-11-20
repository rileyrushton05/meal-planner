import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CACHE_VERSION,
  MAX_AGE_MS,
  SAVE_DELAY_MS,
  STORAGE_KEY,
  clearLastVisit,
  isFromLastVisit,
  keepLastVisit,
  restoreLastVisit,
} from "./persistence";
import { createQueryClient, queryKeys } from "./queryClient";
import type { Account, WeekPlan } from "./types";
import { makeMeal, makeState } from "@/test/factories";
import { saveLastVisit } from "@/test/lastVisit";

const WEEK = "2026-11-16";
const alice: Account = { email: "alice@example.com", is_guest: false, has_recovery_code: true };
const bob: Account = { email: "bob@example.com", is_guest: false, has_recovery_code: true };
const lastWeek = makeState({
  week_start: WEEK,
  meals: [makeMeal({ id: 1, name: "Spaghetti" })],
  plan: [{ day: "Monday", meal_id: 1, servings: 4 }],
});

const saved = () => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  clearLastVisit();
});

describe("restoring the last visit", () => {
  it("puts what was saved in the cache, before anything renders", () => {
    saveLastVisit({ account: alice, state: lastWeek });
    const client = createQueryClient();

    expect(restoreLastVisit(client)).toBe(true);

    expect(client.getQueryData(queryKeys.account)).toEqual(alice);
    expect(client.getQueryData<{ meals: unknown[] }>(queryKeys.library)?.meals).toHaveLength(1);
    expect(client.getQueryData<WeekPlan>(queryKeys.plan(WEEK))?.days).toEqual(lastWeek.plan);
  });

  it("marks every entry as due to be fetched again", () => {
    saveLastVisit({ account: alice, state: lastWeek });
    const client = createQueryClient();

    restoreLastVisit(client);

    const queries = client.getQueryCache().getAll();
    expect(queries).toHaveLength(3);
    expect(queries.every((query) => query.isStale())).toBe(true);
  });

  it("knows restored data from data fetched since", () => {
    saveLastVisit({ state: lastWeek });
    const client = createQueryClient();
    restoreLastVisit(client);
    const restoredAt = client.getQueryState(queryKeys.library)!.dataUpdatedAt;

    expect(isFromLastVisit(queryKeys.library, restoredAt)).toBe(true);

    client.setQueryData(queryKeys.library, { meals: [], ingredient_suggestions: [], templates: [] });
    const fetchedAt = client.getQueryState(queryKeys.library)!.dataUpdatedAt;
    expect(isFromLastVisit(queryKeys.library, fetchedAt)).toBe(false);
    // Nothing at all is not the last visit's either.
    expect(isFromLastVisit(queryKeys.plan("2026-11-23"), 0)).toBe(false);
  });

  it("finds nothing on a first visit", () => {
    expect(restoreLastVisit(createQueryClient())).toBe(false);
  });

  it.each([
    ["written by a build with different API types", { version: "1.another-build" }],
    ["older than two weeks", { savedAt: Date.now() - MAX_AGE_MS - 1 }],
    ["not shaped like a saved copy", { queries: { queries: [{ queryKey: "library" }] } }],
  ])("ignores, and removes, a copy %s", (_, change) => {
    saveLastVisit({ state: lastWeek });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...saved(), ...change }));
    const client = createQueryClient();

    expect(restoreLastVisit(client)).toBe(false);

    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("ignores, and removes, a copy that is not JSON", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");

    expect(restoreLastVisit(createQueryClient())).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("restores only what it keeps, whatever else the copy holds", () => {
    saveLastVisit({ state: lastWeek });
    const copy = saved();
    copy.queries.queries.push({ ...copy.queries.queries[0], queryKey: ["anything"], queryHash: '["anything"]' });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(copy));
    const client = createQueryClient();

    restoreLastVisit(client);

    expect(client.getQueryData(["anything"])).toBeUndefined();
  });

  it("works without storage at all", () => {
    expect(restoreLastVisit(createQueryClient(), null)).toBe(false);
    expect(() => keepLastVisit(createQueryClient(), null)()).not.toThrow();
  });
});

describe("noticing the session belongs to someone else", () => {
  function restoreAs(account: Account) {
    saveLastVisit({ account, state: lastWeek });
    const client = createQueryClient();
    restoreLastVisit(client);
    return client;
  }

  it("resets everything else when the server names another account", () => {
    const client = restoreAs(alice);

    client.setQueryData(queryKeys.account, bob);

    expect(client.getQueryData(queryKeys.library)).toBeUndefined();
    expect(client.getQueryData(queryKeys.plan(WEEK))).toBeUndefined();
    expect(client.getQueryData(queryKeys.account)).toEqual(bob);
  });

  it("keeps everything when it is the same account", () => {
    const client = restoreAs(alice);

    client.setQueryData(queryKeys.account, { ...alice });

    expect(client.getQueryData(queryKeys.library)).toBeDefined();
  });

  it("checks only the first answer: later changes of account reset themselves", () => {
    const client = restoreAs(alice);
    client.setQueryData(queryKeys.account, alice);

    // Signing up turns a guest into an account; the data is the same.
    client.setQueryData(queryKeys.account, bob);

    expect(client.getQueryData(queryKeys.library)).toBeDefined();
  });

  it("leaves the check to the reset when the copy is cleared first", () => {
    // Logging in clears the copy, then resets the cache itself.
    const client = restoreAs(alice);

    clearLastVisit();
    client.setQueryData(queryKeys.account, bob);

    expect(client.getQueryData(queryKeys.library)).toBeDefined();
  });
});

describe("keeping the visit", () => {
  function startKeeping() {
    vi.useFakeTimers();
    const client = createQueryClient();
    const stop = keepLastVisit(client);
    return { client, stop };
  }

  const fill = (client: ReturnType<typeof createQueryClient>) => {
    const { meals, ingredient_suggestions, templates } = lastWeek;
    client.setQueryData(queryKeys.account, alice);
    client.setQueryData(queryKeys.library, { meals, ingredient_suggestions, templates });
  };

  it("saves a moment after the cache changes, gathering changes into one write", () => {
    const { client, stop } = startKeeping();
    const write = vi.spyOn(Storage.prototype, "setItem");

    fill(client);
    expect(write).not.toHaveBeenCalled();
    vi.advanceTimersByTime(SAVE_DELAY_MS);

    expect(write).toHaveBeenCalledTimes(1);
    expect(saved()).toMatchObject({ version: CACHE_VERSION, owner: "account:alice@example.com" });
    stop();
  });

  it("saves at once when the page is left", () => {
    const { client, stop } = startKeeping();
    fill(client);

    window.dispatchEvent(new Event("pagehide"));

    expect(saved()).not.toBeNull();
    stop();
  });

  it("keeps only who is signed in, the meals, plans and grocery lists", () => {
    const { client, stop } = startKeeping();
    fill(client);
    client.setQueryData(["suggestions", WEEK], ["Tacos"]);

    vi.advanceTimersByTime(SAVE_DELAY_MS);

    const keys = saved().queries.queries.map((query: { queryKey: unknown[] }) => query.queryKey[0]);
    expect(keys.sort()).toEqual(["account", "library"]);
    stop();
  });

  it("never keeps a guest's details as anyone's", () => {
    const { client, stop } = startKeeping();
    fill(client);
    client.setQueryData(queryKeys.account, { email: null, is_guest: true, has_recovery_code: false });

    vi.advanceTimersByTime(SAVE_DELAY_MS);

    expect(saved().owner).toBe("guest");
    stop();
  });

  it("removes the copy once there are no meals to show, as after logging out", async () => {
    const { client, stop } = startKeeping();
    fill(client);
    vi.advanceTimersByTime(SAVE_DELAY_MS);

    await client.resetQueries();
    vi.advanceTimersByTime(SAVE_DELAY_MS);

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    stop();
  });

  it("removes the copy rather than leave an old one when storage is full", () => {
    const { client, stop } = startKeeping();
    localStorage.setItem(STORAGE_KEY, "an older copy");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError");
    });

    fill(client);
    expect(() => vi.advanceTimersByTime(SAVE_DELAY_MS)).not.toThrow();

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    stop();
  });

  it("stops saving when told to", () => {
    const { client, stop } = startKeeping();
    stop();

    fill(client);
    vi.advanceTimersByTime(SAVE_DELAY_MS);
    window.dispatchEvent(new Event("pagehide"));

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe("clearing the last visit", () => {
  it("removes the saved copy", () => {
    saveLastVisit({ state: lastWeek });

    clearLastVisit();

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
