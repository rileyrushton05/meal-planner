/**
 * Layout at phone width. A single element that refuses to shrink (a long
 * line in an implicit grid column) widens the whole page, so it scrolls
 * sideways and cuts off controls; screenshots only catch that when someone
 * looks. The new-meal panel once did this when longer templates arrived.
 */

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures.ts";
import { goTo } from "./helpers.ts";

test.use({ viewport: { width: 360, height: 780 } });

async function expectNoSidewaysScroll(page: Page, where: string) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, `${where} scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(0);
}

test("no page scrolls sideways on a phone", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("heading", { name: "This week" }).waitFor();
  await expectNoSidewaysScroll(page, "This week");

  for (const name of ["Meals", "Plan", "Groceries"] as const) {
    await goTo(page, name);
    await expectNoSidewaysScroll(page, name);
  }

  await goTo(page, "Meals");
  await page.getByRole("button", { name: "New meal", exact: true }).click();
  await page.getByText("common meals, ingredients included").waitFor();
  await expectNoSidewaysScroll(page, "the new-meal panel and its templates");

  for (const path of ["/account", "/privacy"]) {
    await page.goto(path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await expectNoSidewaysScroll(page, path);
  }
});
