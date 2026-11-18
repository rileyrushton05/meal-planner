import { readFile } from "node:fs/promises";

import type { Page } from "@playwright/test";

import { expect, test, watchForCspViolations } from "./fixtures.ts";

import {
  addMeal,
  dayPicker,
  goTo,
  mealRow,
  openWeek,
  saveRecoveryCode,
  uniqueName,
} from "./helpers.ts";

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
  await saveRecoveryCode(page);

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

test("take a copy of everything, then delete the account for good", async ({ page }) => {
  const email = `${uniqueName("leaving").replace(" ", "-")}@example.com`;
  const password = "lettuce harbour spoon";
  const mine = uniqueName("Farewell Pie");

  await openWeek(page, "2026-04-13");
  await addMeal(page, mine);
  await page.getByRole("button", { name: "Sign up to keep your meals" }).click();
  const signUp = page.getByRole("dialog", { name: "Create an account" });
  await signUp.getByLabel("Email").fill(email);
  await signUp.getByLabel("Password").fill(password);
  await signUp.getByRole("button", { name: "Create account" }).click();
  await saveRecoveryCode(page);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("link", { name: "Account" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Account");

  // The download is the account's data, readable as it is.
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download my data" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(/^meal-planner-export-.*\.json$/);
  const exported = JSON.parse(await readFile(await download.path(), "utf8"));
  expect(exported.account.email).toBe(email);
  expect(exported.meals.map((meal: { name: string }) => meal.name)).toContain(mine);

  // A wrong password deletes nothing.
  await page.getByRole("button", { name: "Delete account" }).click();
  const confirm = page.getByRole("alertdialog");
  await confirm.getByLabel("Password").fill("not my password");
  await confirm.getByRole("button", { name: "Delete for good" }).click();
  await expect(confirm.getByRole("alert")).toHaveText("That password isn't right.");

  await confirm.getByLabel("Password").fill(password);
  await confirm.getByRole("button", { name: "Delete for good" }).click();

  // Home, in a fresh guest session, with none of it left.
  await expect(page).toHaveURL(/\/\?week=2026-04-13$/);
  await expect(page.getByText(/everything in it have been deleted/)).toBeVisible();
  await expect(page.getByText("You're using a guest session.")).toBeVisible();
  await goTo(page, "Meals");
  await expect(mealRow(page, mine)).toHaveCount(0);

  // And the login is gone with it.
  await page.getByRole("button", { name: "Log in" }).click();
  const logIn = page.getByRole("dialog", { name: "Log in" });
  await logIn.getByLabel("Email").fill(email);
  await logIn.getByLabel("Password").fill(password);
  await logIn.getByRole("button", { name: "Log in" }).click();
  await expect(logIn.getByRole("alert")).toHaveText(
    "That email and password don't match an account.",
  );
});

test("a forgotten password is reset with the recovery code from signup", async ({ page }) => {
  const email = `${uniqueName("forgetful").replace(" ", "-")}@example.com`;
  const mine = uniqueName("Remembered Stew");

  await openWeek(page, "2026-04-20");
  await addMeal(page, mine);
  await page.getByRole("button", { name: "Sign up to keep your meals" }).click();
  const signUp = page.getByRole("dialog", { name: "Create an account" });
  await signUp.getByLabel("Email").fill(email);
  await signUp.getByLabel("Password").fill("lettuce harbour spoon");
  await signUp.getByRole("button", { name: "Create account" }).click();
  const code = await saveRecoveryCode(page);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByText("You're using a guest session.")).toBeVisible();

  // The password is forgotten; the code, typed carelessly, gets back in.
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Forgot your password?" }).click();
  const reset = page.getByRole("dialog", { name: "Reset your password" });
  await reset.getByLabel("Email").fill(email);
  await reset.getByLabel("Recovery code").fill(code.toLowerCase().replaceAll("-", " "));
  await reset.getByLabel("New password").fill("copper kettle meadow");
  await reset.getByRole("button", { name: "Reset password" }).click();

  const next = await saveRecoveryCode(page);
  expect(next).not.toBe(code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await expect(mealRow(page, mine)).toBeVisible();

  // The code was used up: it cannot reset the password again.
  await page.getByRole("button", { name: "Log out" }).click();
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByRole("button", { name: "Forgot your password?" }).click();
  await reset.getByLabel("Email").fill(email);
  await reset.getByLabel("Recovery code").fill(code);
  await reset.getByLabel("New password").fill("another fine password");
  await reset.getByRole("button", { name: "Reset password" }).click();
  await expect(reset.getByRole("alert")).toHaveText(
    "That email and recovery code don't match an account.",
  );
});
