/**
 * The README's screenshots (see playwright.screenshots.config.ts).
 *
 * A first visit starts a guest with the sample meals on four days; a few
 * more are added from the templates and the whole current week planned, so
 * every page has something real to show. All through the app's own API, as
 * the page itself would, against the throwaway database.
 */

import { fileURLToPath } from "node:url";

import { expect, type Locator, type Page, test } from "@playwright/test";

const OUT = fileURLToPath(new URL("../../docs/images/", import.meta.url));

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

/** Monday to Sunday. Sunday cooks for fewer than the recipe serves, so the
 * grocery list's scaling shows. */
const WEEK: readonly [string, number][] = [
  ["Spaghetti Bolognese", 4],
  ["Chicken Stir Fry", 4],
  ["Tacos", 4],
  ["Butter Chicken", 4],
  ["Pad Thai", 4],
  ["Roast Lamb", 6],
  ["Pesto Pasta", 2],
];
/** Ticked off on the grocery list, so it is caught mid-shop. */
const BASKET = ["Bean Sprouts", "Beef Mince", "Cheese"];
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

test.use({ viewport: DESKTOP, deviceScaleFactor: 2 });

/** This week's Monday, as the app writes it: YYYY-MM-DD, local time. */
function mondayOf(today: Date): string {
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${monday.getFullYear()}-${pad(monday.getMonth() + 1)}-${pad(monday.getDate())}`;
}

async function planTheWeek(page: Page, week: string) {
  // The first request finds no session and starts the guest; wait until the
  // app has its state, so the requests below are signed in.
  const loaded = page.waitForResponse((r) => r.url().includes("/api/state") && r.ok());
  await page.goto("/");
  await loaded;
  await page.evaluate(
    async ({ week, plan, days }) => {
      const json = { "Content-Type": "application/json" };
      const have = new Set(
        ((await (await fetch("/api/meals")).json()) as { name: string }[]).map((m) => m.name),
      );
      for (const [name] of plan) {
        if (have.has(name)) continue;
        const added = await fetch(`/api/meals/from-template/${encodeURIComponent(name)}`, {
          method: "POST",
        });
        if (!added.ok) throw new Error(`template ${name}: ${added.status}`);
        have.add(name);
      }
      const meals = (await (await fetch("/api/meals")).json()) as { id: number; name: string }[];
      const id = new Map(meals.map((m) => [m.name, m.id]));
      const saved = await fetch(`/api/plan/${week}`, {
        method: "PUT",
        headers: json,
        body: JSON.stringify({
          days: plan.map(([name, servings], i) => ({
            day: days[i],
            meal_id: id.get(name),
            servings,
          })),
        }),
      });
      if (!saved.ok) throw new Error(`plan: ${saved.status} ${await saved.text()}`);
    },
    { week, plan: WEEK, days: DAYS },
  );
}

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((theme) => localStorage.setItem("theme", theme), theme);
}

async function shoot(page: Page, name: string, only?: Locator) {
  // Let fonts load and transitions finish, so nothing is caught mid-fade.
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(0, 0);
  await page.waitForTimeout(300);
  const options = { path: `${OUT}${name}.png`, animations: "disabled" } as const;
  await (only ? only.screenshot(options) : page.screenshot(options));
}

/**
 * The recipe-import preview, read from the end-to-end tests' fixture site
 * (playwright.config.ts) by the real server. The fixture is served from
 * 127.0.0.1, an odd thing to show in a README, so the page it came from is
 * shown as recipes.example, a domain reserved for examples. Nothing else
 * in the response is touched.
 */
async function importARecipe(page: Page, week: string) {
  await page.route("**/api/recipes/import", async (route) => {
    const response = await route.fetch();
    const recipe = await response.json();
    await route.fulfill({
      response,
      json: { ...recipe, url: "https://recipes.example/weeknight-beef-ragu/" },
    });
  });
  await page.goto(`/meals?week=${week}&meal=new`);
  await page.getByLabel("Recipe link").fill("http://127.0.0.1:4175/ragu.html");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("heading", { name: "Check the recipe" })).toBeVisible();
  await page.unroute("**/api/recipes/import");
}

test("README screenshots", async ({ page }) => {
  const week = mondayOf(new Date());
  await planTheWeek(page, week);

  for (const theme of ["dark", "light"] as const) {
    await setTheme(page, theme);

    await page.goto(`/?week=${week}`);
    await expect(page.getByText("Tonight", { exact: false }).first()).toBeVisible();
    await shoot(page, `this-week-${theme}`);

    await importARecipe(page, week);
    await shoot(page, `import-${theme}`, page.getByRole("region", { name: "New meal" }));

    if (theme === "light") continue;

    await page.goto(`/meals?week=${week}`);
    await page.getByRole("article", { name: "Pad Thai", exact: true }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Pad Thai" })).toBeVisible();
    await shoot(page, "meals");

    await page.goto(`/groceries?week=${week}`);
    await expect(page.getByLabel("Week starting")).toHaveValue(week);
    // Part way round the shop: a few things already in the basket.
    for (const item of BASKET) {
      await page.getByRole("checkbox", { name: new RegExp(`^${item}`) }).check();
    }
    await shoot(page, "groceries");
  }

  await setTheme(page, "dark");
  await page.setViewportSize(PHONE);
  await page.goto(`/groceries?week=${week}`);
  await expect(page.getByLabel("Week starting")).toHaveValue(week);
  await shoot(page, "groceries-phone");
});
