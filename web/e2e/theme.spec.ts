/**
 * The theme: dark by default, and a choice that survives a reload, applied
 * before the app has even started (public/theme.js), so it never flashes.
 */

import { expect, test } from "./fixtures.ts";

const html = (page: import("@playwright/test").Page) => page.locator("html");

test("dark by default; a chosen theme is there from the first paint after a reload", async ({
  page,
}) => {
  await page.goto("/");
  await expect(html(page)).toHaveClass(/\bdark\b/);

  await page.getByRole("button", { name: "Light theme" }).click();
  await expect(html(page)).not.toHaveClass(/\bdark\b/);

  // Hold back the app's own code: whatever theme shows now was put there by
  // the pre-paint script alone.
  await page.route("**/src/main.tsx", (route) => route.abort());
  await page.route("**/assets/*.js", (route) => route.abort());
  await page.reload();
  await expect(html(page)).not.toHaveClass(/\bdark\b/);
});

test("the device's own setting does not override the choice", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(html(page)).toHaveClass(/\bdark\b/);
  await expect(page.getByRole("button", { name: /theme$/ })).toHaveCount(2);
});
