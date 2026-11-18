/**
 * The flows the app exists for, in a real browser against the real API.
 *
 * Each spec works in its own week and names its own meals, so they do not
 * depend on each other or on the order they run in.
 */

import { expect, test } from "./fixtures.ts";

import {
  addMeal,
  dayPicker,
  goTo,
  mealRow,
  mealSearch,
  openWeek,
  pageLink,
  planDay,
  uniqueName,
} from "./helpers.ts";

test("add a meal", async ({ page }) => {
  await openWeek(page, "2026-01-05");
  const name = uniqueName("Lentil Soup");

  await addMeal(page, name, 6);

  await expect(page.getByText("Serves 6 · 0 ingredients")).toBeVisible();
});

test("add a meal from a template, ingredients included", async ({ page }) => {
  await openWeek(page, "2026-01-05");

  await page.getByRole("button", { name: "New meal", exact: true }).click();
  await page.getByRole("button", { name: "Add Chicken Stir Fry" }).click();

  // It opens, ingredients and all.
  await expect(page.getByRole("heading", { level: 2, name: "Chicken Stir Fry" })).toBeVisible();
  await expect(mealRow(page, "Chicken Stir Fry")).toContainText("Serves 4 · 5 ingredients");
  // The template is marked as added, so it cannot be added twice.
  await page.getByRole("button", { name: "New meal", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Chicken Stir Fry (added)" }),
  ).toBeDisabled();
});

test("add ingredients straight after creating a meal, and edit an amount", async ({ page }) => {
  await openWeek(page, "2026-01-05");
  const name = uniqueName("Fried Rice");
  await addMeal(page, name);

  // No hunting for the meal: it is open, and the cursor is waiting.
  await expect(page.getByLabel("Ingredient", { exact: true })).toBeFocused();
  await page.keyboard.type("Rice");
  await page.getByLabel("Quantity", { exact: true }).fill("200");
  await page.getByLabel("Unit", { exact: true }).fill("g");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("200 g");
  // Ready for the next one.
  await expect(page.getByLabel("Ingredient", { exact: true })).toBeFocused();

  await page.getByRole("button", { name: "Edit Rice" }).click();
  await page.getByLabel("Quantity of Rice").fill("300");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("300 g");

  // Saved to the server, and the URL reopens the same meal.
  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Rice" })).toContainText("300 g");
});

test("plan a week: it saves itself, and survives a reload", async ({ page }) => {
  await openWeek(page, "2026-01-12");
  const name = uniqueName("Shakshuka");
  await addMeal(page, name, 2);

  await goTo(page, "Plan");
  await planDay(page, "Monday", name);
  // The recipe's own serving size, until changed.
  await expect(page.getByRole("listitem", { name: "Monday" })).toContainText("Serves2");
  await page.getByRole("button", { name: "More servings on Monday" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // The URL keeps the page and week, so a reload lands on the saved plan.
  await page.reload();
  await expect(page).toHaveURL(/\/plan\?week=2026-01-12$/);
  await expect(pageLink(page, "Plan")).toHaveAttribute("aria-current", "page");
  await expect(dayPicker(page, "Monday")).toHaveAccessibleName(`Monday: ${name}`);
  await expect(page.getByRole("listitem", { name: "Monday" })).toContainText("Serves3");
});

test("plan a meal that does not exist yet, from the plan itself", async ({ page }) => {
  await openWeek(page, "2026-01-12", "plan");
  const name = uniqueName("Fish Pie");

  await dayPicker(page, "Thursday").click();
  const search = mealSearch(page, "Thursday");
  await expect(search.getByRole("combobox", { name: "Search meals" })).toBeFocused();
  await page.keyboard.type(name);
  await search.getByRole("option", { name: new RegExp(`New meal “${name}”`) }).click();

  await expect(dayPicker(page, "Thursday")).toHaveAccessibleName(`Thursday: ${name}`);
  await goTo(page, "Meals");
  await expect(mealRow(page, name)).toBeVisible();
});

test("the grocery list totals the week and converts units", async ({ page }) => {
  await openWeek(page, "2026-01-19");
  // One of the sample meals every guest starts with.
  await expect(mealRow(page, "Spaghetti Bolognese")).toBeVisible();

  await goTo(page, "Plan");
  await planDay(page, "Monday", "Spaghetti Bolognese");
  await planDay(page, "Tuesday", "Spaghetti Bolognese");

  // The list is there on arrival: no button to press first.
  await goTo(page, "Groceries");

  // Two nights of a recipe using 400 g pasta and 500 g mince.
  const pasta = page.getByRole("checkbox", { name: "Pasta 800 g" });
  await expect(pasta).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Beef Mince 1 kg" })).toBeVisible();

  // Ticked off, it drops into the basket, and stays there after a reload.
  await pasta.check();
  const basket = page.getByRole("region", { name: /^In the basket/ });
  await expect(basket.getByRole("checkbox", { name: "Pasta 800 g" })).toBeChecked();
  await page.reload();
  await expect(basket.getByRole("checkbox", { name: "Pasta 800 g" })).toBeChecked();
});

test("copy last week's plan forward, and undo it", async ({ page }) => {
  await openWeek(page, "2026-01-26");
  const name = uniqueName("Pho");
  await addMeal(page, name);
  await goTo(page, "Plan");
  await planDay(page, "Wednesday", name);

  await page.getByRole("button", { name: "Next week" }).click();
  await expect(page.getByLabel("Week starting")).toHaveValue("2026-02-02");
  await expect(dayPicker(page, "Wednesday")).toHaveAccessibleName("Wednesday: no meal");
  await page.getByRole("button", { name: "Copy last week" }).click();
  await expect(dayPicker(page, "Wednesday")).toHaveAccessibleName(`Wednesday: ${name}`);

  await page.getByRole("button", { name: "Undo copying last week" }).click();
  await expect(dayPicker(page, "Wednesday")).toHaveAccessibleName("Wednesday: no meal");
});

test("home: plan the focal day in place, then any other day in one click", async ({ page }) => {
  const soup = uniqueName("Pumpkin Soup");
  const pie = uniqueName("Fish Pie");
  await openWeek(page, "2026-02-09");
  await addMeal(page, soup);
  await addMeal(page, pie);

  // A week other than this one is about its Monday.
  await goTo(page, "This week");
  const monday = page.getByRole("region", { name: /^Monday/ });
  await expect(monday).toContainText("Nothing planned yet");
  const saved = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("/api/plan/"),
  );
  await page.getByRole("button", { name: "Choose a meal for Monday" }).click();
  const mondaySearch = mealSearch(page, "Monday");
  await expect(mondaySearch.getByRole("combobox", { name: "Search meals" })).toBeFocused();
  await page.keyboard.type(soup);
  await expect(mondaySearch.getByRole("option").first()).toContainText(soup);
  await page.keyboard.press("Enter");
  expect((await saved).ok()).toBe(true);
  await expect(monday).toContainText(soup);
  await expect(page.getByRole("link", { name: /^Nights planned/ })).toContainText("1of 7");

  // The next night to plan is a click away, its search already open.
  await page.getByRole("link", { name: /^Nights planned/ }).click();
  await expect(page).toHaveURL(/\/plan\?week=2026-02-09$/);
  const tuesdaySearch = mealSearch(page, "Tuesday");
  await expect(tuesdaySearch.getByRole("combobox", { name: "Search meals" })).toBeFocused();
  const second = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("/api/plan/"),
  );
  await page.keyboard.type(pie);
  await expect(tuesdaySearch.getByRole("option").first()).toContainText(pie);
  await page.keyboard.press("Enter");
  expect((await second).ok()).toBe(true);
  await expect(dayPicker(page, "Tuesday")).toHaveAccessibleName(`Tuesday: ${pie}`);

  // Back home, the week shows both, and the count of things to buy is real.
  await goTo(page, "This week");
  const week = page.getByRole("region", { name: "The week" });
  await expect(week.getByRole("link", { name: /^Tuesday/ })).toContainText(pie);
  await expect(page.getByRole("link", { name: /^To buy/ })).toContainText("0items");
});
