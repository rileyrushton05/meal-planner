/**
 * The last visit's data, kept in the browser so the next visit shows it at
 * once.
 *
 * After a quiet spell, the first request waits for a serverless function to
 * start and a database to wake up: one to three seconds on the free tiers
 * this runs on. Rather than a blank page for that long, the app shows what
 * it had last time, straight from `localStorage`, and fetches the real thing
 * behind it. Kept data is a starting point and never the answer: everything
 * restored is due to be fetched again, and until it has been the page is
 * read-only (`usePlanner`'s `freshness`), because a change made to old data
 * could undo one made since on another device.
 *
 * What is kept: who is signed in, the meals, and the plans and grocery lists
 * of the weeks recently looked at. Nothing else: no change waiting to be
 * sent, and no recovery code (those never enter the cache). The copy belongs
 * to this browser's session just as the session cookie does, and goes with
 * it: logging out, logging in as someone else and deleting the account all
 * clear it (`useAccount`).
 *
 * A saved copy is ignored when it is older than `MAX_AGE_MS`, or when the
 * build that wrote it had different API types (`CACHE_VERSION`), so a deploy
 * that changes the data's shape never hands a page something it cannot read.
 */

import { dehydrate, hashKey, hydrate, type QueryClient, type QueryKey } from "@tanstack/react-query";

import { queryKeys } from "./queryClient";
import type { Account } from "./types";

export const STORAGE_KEY = "fridge-door:last-visit";

/** Bump when what is kept changes shape while the API's types do not: a
 *  query key renamed, a cache entry reshaped. */
const FORMAT = 1;

/** Which build's data a copy holds. See `cacheVersion` in vite.config.ts. */
export const CACHE_VERSION = `${FORMAT}.${import.meta.env.VITE_CACHE_VERSION ?? "dev"}`;

/** Older than this, a copy is more likely to mislead than to help. */
export const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;

/** Saves are gathered up: one page load fills several cache entries. */
export const SAVE_DELAY_MS = 500;

/** The cache entries kept, by the first part of their query key. */
const KEPT = new Set<unknown>([
  queryKeys.account[0],
  queryKeys.library[0],
  queryKeys.plans[0],
  queryKeys.groceries[0],
]);

interface Snapshot {
  version: string;
  savedAt: number;
  /** Whose data this is (`ownerOf`), to notice a session that now
   *  belongs to someone else. */
  owner: string | null;
  queries: ReturnType<typeof dehydrate>;
}

/** Each restored entry's hash, with the moment its data was fetched. */
const restored = new Map<string, number>();
/** Set by a restore until the server has said who is signed in. */
let unconfirmedOwner: string | null = null;
let stopWatchingAccount: (() => void) | null = null;

/**
 * Whether an entry is still showing what a restore put there. Once the
 * server answers, `dataUpdatedAt` moves on and this is false.
 */
export function isFromLastVisit(queryKey: QueryKey, dataUpdatedAt: number): boolean {
  return dataUpdatedAt > 0 && restored.get(hashKey(queryKey)) === dataUpdatedAt;
}

/**
 * Put the last visit's data in the cache, before the first render, so the
 * first paint already shows it. Returns whether there was any.
 *
 * Every entry is marked out of date, so each page fetches what it shows as
 * it mounts. If the server then says a different account is signed in
 * (another tab logged in as someone else, say), everything but the account
 * is reset, as logging in does.
 */
export function restoreLastVisit(client: QueryClient, storage: Storage | null = browserStorage()) {
  restored.clear();
  stopWatchingAccount?.();
  stopWatchingAccount = null;
  unconfirmedOwner = null;

  const snapshot = read(storage);
  if (!snapshot) return false;

  hydrate(client, snapshot.queries);
  for (const query of snapshot.queries.queries) {
    restored.set(query.queryHash, query.state.dataUpdatedAt);
  }
  void client.invalidateQueries({ refetchType: "none" });

  unconfirmedOwner = snapshot.owner;
  const accountHash = hashKey(queryKeys.account);
  stopWatchingAccount = client.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" || event.action.type !== "success") return;
    if (event.query.queryHash !== accountHash) return;
    const signedIn = ownerOf(event.query.state.data as Account | undefined);
    const shown = unconfirmedOwner;
    stopWatchingAccount?.();
    stopWatchingAccount = null;
    unconfirmedOwner = null;
    if (shown !== null && signedIn !== shown) {
      void client.resetQueries({ predicate: (query) => query.queryHash !== accountHash });
    }
  });
  return true;
}

/**
 * Save the cache as it changes, a moment after each change and at once when
 * the page is hidden or closed. Returns a function that stops saving.
 */
export function keepLastVisit(
  client: QueryClient,
  storage: Storage | null = browserStorage(),
): () => void {
  if (!storage) return () => {};

  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    clearTimeout(timer);
    timer = undefined;
    write(storage, client);
  };

  const unsubscribe = client.getQueryCache().subscribe((event) => {
    const changed =
      event.type === "removed" ||
      (event.type === "updated" &&
        (event.action.type === "success" || event.action.type === "setState"));
    if (changed) timer ??= setTimeout(save, SAVE_DELAY_MS);
  });

  // A tab being closed may never run the timer.
  const saveIfDue = () => {
    if (timer !== undefined) save();
  };
  const onHidden = () => {
    if (document.visibilityState === "hidden") saveIfDue();
  };
  window.addEventListener("pagehide", saveIfDue);
  document.addEventListener("visibilitychange", onHidden);

  return () => {
    clearTimeout(timer);
    unsubscribe();
    window.removeEventListener("pagehide", saveIfDue);
    document.removeEventListener("visibilitychange", onHidden);
  };
}

/** Forget the saved copy: its account is no longer the one signed in. */
export function clearLastVisit(storage: Storage | null = browserStorage()) {
  unconfirmedOwner = null;
  stopWatchingAccount?.();
  stopWatchingAccount = null;
  try {
    storage?.removeItem(STORAGE_KEY);
  } catch {
    // Storage that cannot be written holds nothing to clear.
  }
}

/**
 * Who a copy belongs to: an account's email, or "guest". Two guest sessions
 * in one browser are not told apart; they are the same person, and both
 * see their data fetched again before they can change anything.
 */
function ownerOf(account: Account | undefined): string | null {
  if (!account) return null;
  return account.is_guest ? "guest" : `account:${account.email ?? ""}`;
}

function write(storage: Storage, client: QueryClient) {
  try {
    // Nothing worth showing without the meals: after logging out, say.
    if (!client.getQueryData(queryKeys.library)) {
      storage.removeItem(STORAGE_KEY);
      return;
    }
    const snapshot: Snapshot = {
      version: CACHE_VERSION,
      savedAt: Date.now(),
      owner: ownerOf(client.getQueryData<Account>(queryKeys.account)),
      queries: dehydrate(client, {
        shouldDehydrateQuery: (query) =>
          query.state.status === "success" && KEPT.has(query.queryKey[0]),
      }),
    };
    storage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Full, or refused (some private modes). The app works without it; a
    // half-written or outdated copy must not stay behind, though.
    try {
      storage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing more to do.
    }
  }
}

function read(storage: Storage | null): Snapshot | null {
  if (!storage) return null;
  let snapshot: unknown;
  try {
    const saved = storage.getItem(STORAGE_KEY);
    if (saved === null) return null;
    snapshot = JSON.parse(saved);
  } catch {
    snapshot = null;
  }
  if (isUsable(snapshot)) {
    return {
      ...snapshot,
      queries: {
        mutations: [],
        queries: snapshot.queries.queries.filter((query) => KEPT.has(query.queryKey[0])),
      },
    };
  }
  clearLastVisit(storage);
  return null;
}

function isUsable(value: unknown): value is Snapshot {
  if (typeof value !== "object" || value === null) return false;
  const snapshot = value as Partial<Snapshot>;
  const age = Date.now() - (snapshot.savedAt ?? Number.NaN);
  return (
    snapshot.version === CACHE_VERSION &&
    // Negative only if the clock went back since; that is no reason to
    // throw the copy away.
    age < MAX_AGE_MS &&
    Array.isArray(snapshot.queries?.queries) &&
    snapshot.queries.queries.every(
      (query) => Array.isArray(query?.queryKey) && typeof query.state?.dataUpdatedAt === "number",
    )
  );
}

/**
 * `localStorage`, or null where using it throws (storage blocked, some
 * private windows): the app then simply starts empty, as it always did.
 */
function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
