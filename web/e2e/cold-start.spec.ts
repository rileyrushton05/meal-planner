/**
 * Opening the app while the server is slow to answer, as it is after a
 * quiet spell: a return visit shows the last one's data at once, read-only
 * until the real data arrives; a first visit shows the page's outline.
 *
 * The slow server is played by holding `/api/state` until the test lets it
 * through, so nothing here depends on timing.
 */

import type { Page, Route } from "@playwright/test";

import { expect, test } from "./fixtures.ts";
import { addMeal, mealRow, openWeek, uniqueName } from "./helpers.ts";

const STORAGE_KEY = "fridge-door:last-visit";

/** Hold every request to `/api/state` until `release` is called. */
async function holdState(page: Page) {
  let release!: () => void;
  const released = new Promise<void>((resolve) => (release = resolve));
  const held: string[] = [];
  await page.route("**/api/state**", async (route: Route) => {
    held.push(route.request().url());
    await released;
    await route.continue();
  });
  return { release, held };
}

/** Everything the page has asked the API for since this was called. */
function apiReads(page: Page) {
  const reads: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "GET" && url.pathname.startsWith("/api/")) reads.push(url.pathname);
  });
  return reads;
}

/** Wait until the browser's copy of the visit includes `text`. */
async function keptCopyIncludes(page: Page, text: string) {
  await expect
    .poll(() => page.evaluate((key) => localStorage.getItem(key) ?? "", STORAGE_KEY))
    .toContain(text);
}

/** The page's content: the part made inert while it shows old data. */
const content = (page: Page) => page.locator("main [aria-busy]");

test("a return visit shows the last one at once, read-only until it is up to date", async ({
  page,
}) => {
  await openWeek(page, "2026-03-02");
  const name = uniqueName("Leftover Curry");
  await addMeal(page, name);
  await keptCopyIncludes(page, name);

  const server = await holdState(page);
  const reads = apiReads(page);
  await page.reload();

  // The server has not answered, and the meal is already there.
  await expect(mealRow(page, name)).toBeVisible();
  expect(server.held).toHaveLength(1);
  await expect(page.getByRole("status").filter({ hasText: "Updating…" })).toBeVisible();
  await expect(content(page)).toHaveAttribute("inert", "");

  server.release();

  await expect(page.getByText("Updating…")).toBeHidden();
  await expect(content(page)).not.toHaveAttribute("inert");
  // Usable again: the meal opens.
  await mealRow(page, name).getByRole("button").click();
  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  // One request brought it all up to date, as on any first load.
  expect(reads.filter((path) => path === "/api/state")).toHaveLength(1);
  expect(reads.filter((path) => path.startsWith("/api/plan"))).toHaveLength(0);
});

test("when the server cannot be reached, the last visit stays readable", async ({ page }) => {
  await openWeek(page, "2026-03-09");
  const name = uniqueName("Offline Soup");
  await addMeal(page, name);
  await keptCopyIncludes(page, name);

  await page.route("**/api/state**", (route) => route.abort("internetdisconnected"));
  await page.reload();

  await expect(mealRow(page, name)).toBeVisible();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Couldn't reach the server.");
  await expect(alert).toContainText("You're seeing what you had last time");
  await expect(page.getByText("Last visit's copy")).toBeVisible();
  await expect(content(page)).toHaveAttribute("inert", "");

  await page.unroute("**/api/state**");
  await alert.getByRole("button", { name: "Try again" }).click();

  await expect(page.getByText("Last visit's copy")).toBeHidden();
  await expect(page.getByRole("alert")).toBeHidden();
  await expect(content(page)).not.toHaveAttribute("inert");
});

test("a first visit shows the page's outline, and says why it is slow", async ({ page }) => {
  const server = await holdState(page);

  await page.goto("/groceries?week=2026-03-16");

  const loading = page.getByRole("status").filter({ hasText: "Loading…" });
  await expect(loading).toHaveAttribute("aria-busy", "true");
  await expect(page.getByText(/waking the server up/i)).toBeVisible({ timeout: 5_000 });

  server.release();

  await expect(page.getByRole("textbox", { name: "Add something else" })).toBeVisible();
  await expect(loading).toBeHidden();
});

test("deleting a guest session leaves none of it in the browser", async ({ page }) => {
  await openWeek(page, "2026-03-23");
  const name = uniqueName("Secret Recipe");
  await addMeal(page, name);
  await keptCopyIncludes(page, name);

  await page.goto("/account");
  await page.getByRole("button", { name: "Delete everything" }).click();
  await page.getByRole("button", { name: "Delete for good" }).click();
  await expect(page.getByText(/Everything from that guest session has been deleted/)).toBeVisible();

  // The new guest's meals are kept now, and nothing of the old one's.
  await keptCopyIncludes(page, '"meals"');
  const kept = await page.evaluate((key) => localStorage.getItem(key) ?? "", STORAGE_KEY);
  expect(kept).not.toContain(name);
});
