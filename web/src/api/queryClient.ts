/**
 * Server state is held by TanStack Query, one cache entry per resource.
 *
 * Every change to the data goes through this client, and each mutation
 * patches the cache from the API's response. So nothing goes stale behind
 * the app's back, and cached data needs no background refetch: a week
 * visited once is served from memory for the rest of the visit. (Grocery
 * lists are the exception: ticks are shared, so they refresh while shown.)
 *
 * The cache also outlives the visit: persistence.ts keeps it in the browser,
 * so the next visit starts from it and fetches it again behind the scenes.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryKeys = {
  /** Who is signed in. */
  account: ["account"] as const,
  /** Meals, ingredient names and templates: everything not tied to a week. */
  library: ["library"] as const,
  plans: ["plan"] as const,
  plan: (week: string) => ["plan", week] as const,
  groceries: ["grocery"] as const,
  grocery: (week: string) => ["grocery", week] as const,
};

/** How long an entry no page is showing stays in memory, and so in the
 *  copy persistence.ts saves: a day, so a week looked at this morning is
 *  still there this evening. Each is a few kilobytes. */
const UNUSED_ENTRY_LIFETIME_MS = 24 * 60 * 60 * 1000;

export function createQueryClient({ retry = 1 }: { retry?: number | false } = {}) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: UNUSED_ENTRY_LIFETIME_MS,
        refetchOnWindowFocus: false,
        retry,
      },
      mutations: { retry: false },
    },
  });
}
