/**
 * Entering a whole ingredient list at once: paste it, or import it from a
 * recipe page, check it, save it.
 */

import { expect, test } from "./fixtures.ts";

import { addMeal, goTo, openWeek, planDay, uniqueName } from "./helpers.ts";

const RECIPE = `Ingredients
500g beef mince
1 brown onion, finely diced
2-3 garlic cloves, crushed
1 x 400 g can chopped tomatoes
2 tbsp tomato paste
1 cup beef stock
400 g spaghetti
Salt and pepper, to taste`;

test("paste eight ingredient lines, check them, and save them in one request", async ({
  page,
}) => {
  await openWeek(page, "2026-02-02");
  const name = uniqueName("Pasted Bolognese");
  await addMeal(page, name);

  await page.getByRole("button", { name: "Paste a list" }).click();
  await page.getByLabel("Paste the ingredient list").fill(RECIPE);
  await page.getByRole("button", { name: "Read 9 lines" }).click();

  // "Ingredients" is a heading, not an ingredient: it has no amount, so it
  // cannot be saved until it is removed.
  const save = page.getByRole("button", { name: /^Save \d+ ingredients$/ });
  await expect(save).toBeDisabled();
  await page.getByRole("button", { name: "Remove line 1", exact: true }).click();

  // Read as a person means them, with the doubts shown.
  await expect(page.getByLabel("Ingredient on line 1")).toHaveValue("Beef Mince");
  await expect(page.getByLabel("Unit on line 3")).toHaveValue("cloves");
  await expect(page.getByText("Read 2 to 3 as 3.")).toBeVisible();
  await expect(page.getByLabel("Ingredient on line 4")).toHaveValue("Diced Tomatoes");
  await expect(page.getByLabel("Quantity on line 4")).toHaveValue("400");

  // Salt "to taste" has no amount either; it is not bought by the gram.
  await expect(page.getByLabel("Ingredient on line 8")).toHaveValue("Salt and pepper");
  await page.getByRole("button", { name: "Remove line 8", exact: true }).click();

  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/ingredients")) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  await page.getByRole("button", { name: "Save 7 ingredients" }).click();

  await expect(page.getByText(`Serves 4 · 7 ingredients`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Garlic" })).toContainText("3 cloves");
  expect(writes).toEqual([expect.stringMatching(/^PUT \/api\/meals\/\d+\/ingredients$/)]);

  // On the grocery list once planned, adding up like any other meal.
  await goTo(page, "Plan");
  await planDay(page, "Monday", name);
  await goTo(page, "Groceries");
  await expect(page.getByText("Beef Mince", { exact: true })).toBeVisible();
});

test("import a recipe from a link, check it, and create the meal in one request", async ({
  page,
}) => {
  await openWeek(page, "2026-02-09");
  await page.getByRole("button", { name: "New meal", exact: true }).click();

  // The fixture site (playwright.config.ts) stands in for a recipe website.
  await page.getByLabel("Recipe link").fill("http://127.0.0.1:4175/ragu.html");
  await page.getByRole("button", { name: "Import" }).click();

  await expect(page.getByRole("heading", { name: "Check the recipe" })).toBeVisible();
  const name = uniqueName("Imported Ragu");
  await page.getByLabel("Meal name").fill(name);
  await expect(page.getByLabel("Servings")).toHaveValue("6");
  await expect(page.getByLabel("Ingredient on line 4")).toHaveValue("Diced Tomatoes");
  await expect(page.getByLabel("Quantity on line 4")).toHaveValue("800");
  // "Salt and pepper, to taste" has no amount to buy.
  await page.getByRole("button", { name: "Remove it" }).click();

  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(new URL(request.url()).pathname);
  });
  await page.getByRole("button", { name: "Create meal with 6 ingredients" }).click();

  await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  await expect(page.getByText("Serves 6 · 6 ingredients")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Garlic" })).toContainText("2 cloves");
  expect(writes).toEqual(["/api/meals"]);
});

test("a link to an address on this network is refused, and says why", async ({ page }) => {
  await openWeek(page, "2026-02-09");
  await page.getByRole("button", { name: "New meal", exact: true }).click();

  await page.getByLabel("Recipe link").fill("http://127.0.0.1:8001/health/live");
  await page.getByRole("button", { name: "Import" }).click();

  await expect(page.getByText("That address can't be fetched from here.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Check the recipe" })).toHaveCount(0);
});
