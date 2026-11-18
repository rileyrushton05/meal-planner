import type { Page } from "@playwright/test";

import { expect, test, watchForCspViolations } from "./fixtures.ts";

import { addMeal, dayPicker, goTo, mealRow, openWeek, uniqueName } from "./helpers.ts";

test("each visitor gets their own guest session, invisible to anyone else", async ({
  browser,
}) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  try {
    const mine = await first.newPage();
    const theirs = await second.newPage();
    const violations = [mine, theirs].map(watchForCspViolations);
    const name = uniqueName("Private Lasagne");

    await openWeek(mine, "2026-03-02");
    await addMeal(mine, name);

    await openWeek(theirs, "2026-03-02");
    await expect(theirs.getByLabel("Search meals")).toBeVisible();
    await expect(mealRow(theirs, name)).toHaveCount(0);

    // The first visitor's session survives a reload: the cookie is the account.
    await mine.reload();
    await expect(mealRow(mine, name)).toBeVisible();

    const cookies = await first.cookies();
    const session = cookies.find((cookie) => cookie.name === "__Host-session");
    expect(session).toMatchObject({ httpOnly: true, secure: true, sameSite: "Strict" });
    expect(violations.flat(), "Content-Security-Policy violations").toEqual([]);
  } finally {
    await first.close();
    await second.close();
  }
});

test("a first visit lands in a guest session with sample meals planned this week", async ({
  page,
}) => {
  await page.goto("/");

  // Home is this week, already part filled.
  await expect(page.getByText("You're using a guest session.")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("This week");
  await expect(
    page.getByRole("region", { name: "The week" }).getByRole("link", { name: /^Monday/ }),
  ).toContainText("Spaghetti Bolognese");

  await goTo(page, "Plan");
  await expect(dayPicker(page, "Monday")).toHaveAccessibleName("Monday: Spaghetti Bolognese");
  await expect(dayPicker(page, "Wednesday")).toHaveAccessibleName("Wednesday: no meal");

  await goTo(page, "Meals");
  for (const meal of ["Spaghetti Bolognese", "Tacos", "Butter Chicken"]) {
    await expect(page.getByRole("article", { name: meal })).toBeVisible();
  }
});

const sessionCookie = async (page: Page) =>
  (await page.context().cookies()).find((cookie) => cookie.name === "__Host-session")?.value;

test("signing up keeps everything made as a guest, under a new session", async ({ page }) => {
  const email = `${uniqueName("cook").replace(" ", "-")}@example.com`;
  const password = "lettuce harbour spoon";
  const mine = uniqueName("Guest Risotto");

  await openWeek(page, "2026-04-06");
  await addMeal(page, mine);
  const guestCookie = await sessionCookie(page);

  await page.getByRole("button", { name: "Sign up to keep your meals" }).click();
  const signUp = page.getByRole("dialog", { name: "Create an account" });
  await signUp.getByLabel("Email").fill(email);
  await signUp.getByLabel("Password").fill(password);
  await signUp.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await expect(mealRow(page, mine)).toBeVisible();
  expect(await sessionCookie(page)).not.toBe(guestCookie);

  // Still signed in, with the same meals, after a reload.
  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await expect(mealRow(page, mine)).toBeVisible();

  // Logging out starts a fresh guest; logging back in brings the meal back.
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByText("You're using a guest session.")).toBeVisible();
  await expect(mealRow(page, mine)).toHaveCount(0);

  await page.getByRole("button", { name: "Log in" }).click();
  const logIn = page.getByRole("dialog", { name: "Log in" });
  await logIn.getByLabel("Email").fill(email);
  await logIn.getByLabel("Password").fill("lettuce harbour fork");
  await logIn.getByRole("button", { name: "Log in" }).click();
  await expect(logIn.getByRole("alert")).toHaveText(
    "That email and password don't match an account.",
  );

  await logIn.getByLabel("Password").fill(password);
  await logIn.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await expect(mealRow(page, mine)).toBeVisible();
});
