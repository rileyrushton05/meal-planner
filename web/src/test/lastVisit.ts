import { keepLastVisit } from "@/api/persistence";
import { createQueryClient, queryKeys } from "@/api/queryClient";
import type { Account, AppState, GroceryList, WeekPlan } from "@/api/types";

/** What a previous visit might have left behind. */
export interface LastVisit {
  account?: Account;
  state: AppState;
  groceries?: GroceryList[];
}

/**
 * Save a previous visit's data the way the app does, through a cache of
 * its own, dated a minute ago (as a real one would be, so nothing fetched
 * in the test can share its timestamp).
 */
export function saveLastVisit(visit: LastVisit, storage: Storage = localStorage) {
  const client = createQueryClient();
  const stop = keepLastVisit(client, storage);
  const updatedAt = Date.now() - 60_000;
  if (visit.account) client.setQueryData(queryKeys.account, visit.account, { updatedAt });
  const { meals, ingredient_suggestions, templates, week_start, plan } = visit.state;
  client.setQueryData(queryKeys.library, { meals, ingredient_suggestions, templates }, { updatedAt });
  client.setQueryData<WeekPlan>(
    queryKeys.plan(week_start),
    { week_start, days: plan },
    { updatedAt },
  );
  for (const list of visit.groceries ?? []) {
    client.setQueryData(queryKeys.grocery(list.week_start), list, { updatedAt });
  }
  // Leaving the page saves at once, as closing the tab would.
  window.dispatchEvent(new Event("pagehide"));
  stop();
}
