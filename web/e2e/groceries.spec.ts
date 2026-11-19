import { expect, test, watchForCspViolations } from "./fixtures.ts";
import { goTo, mealRow, openWeek, planDay } from "./helpers.ts";

test("a tick made on one device shows on another signed in as the same person", async ({
  page,
  browser,
}) => {
  await openWeek(page, "2026-02-02");
  await expect(mealRow(page, "Spaghetti Bolognese")).toBeVisible();
  await goTo(page, "Plan");
  await planDay(page, "Monday", "Spaghetti Bolognese");
  await goTo(page, "Groceries");

  const saved = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("/checks"),
  );
  await page.getByRole("checkbox", { name: "Pasta 400 g" }).check();
  expect((await saved).status()).toBe(204);

  // A second browser with the same person's session: a phone, say.
  const phoneContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  await phoneContext.addCookies(await page.context().cookies());
  const phone = await phoneContext.newPage();
  const violations = watchForCspViolations(phone);
  try {
    await openWeek(phone, "2026-02-02", "groceries");
    const phoneBasket = phone.getByRole("region", { name: /^In the basket/ });
    await expect(phoneBasket.getByRole("checkbox", { name: "Pasta 400 g" })).toBeChecked();

    // And back: unticked on the phone, gone from the laptop's basket.
    const unticked = phone.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/checks"),
    );
    // Not looked for in the basket: unticked, it leaves it, and the basket
    // with it, and Playwright looks again to confirm the box is clear.
    await phone.getByRole("checkbox", { name: "Pasta 400 g" }).uncheck();
    await unticked;
    await page.reload();
    await expect(
      page.getByRole("region", { name: /^To get/ }).getByRole("checkbox", { name: "Pasta 400 g" }),
    ).not.toBeChecked();
    expect(violations).toEqual([]);
  } finally {
    await phoneContext.close();
  }
});

test("extras, usuals, things already at home and the aisle order all stay put", async ({
  page,
}) => {
  await openWeek(page, "2026-02-09");
  await goTo(page, "Plan");
  await planDay(page, "Monday", "Spaghetti Bolognese");
  await goTo(page, "Groceries");

  // An extra, typed as it would be said.
  await page.getByRole("textbox", { name: "Add something else" }).fill("2 L milk");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Milk extra 2 L" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Add something else" })).toHaveValue("");

  // Kept as a usual, from its menu. Each menu's items are looked for in
  // that menu, and each menu is gone before the next opens: a closing menu
  // fades out for a moment, and on CI's slower machines the next one opened
  // while the last was still there, with an "Already have it" of its own.
  await page.getByRole("button", { name: "More for Milk" }).click();
  const milkMenu = page.getByRole("menu", { name: "More for Milk" });
  await milkMenu.getByRole("menuitem", { name: "Keep as a usual" }).click();
  await expect(milkMenu).toBeHidden();
  await expect(page.getByRole("button", { name: /^My usuals/ })).toContainText("1");

  // Something already in the cupboard.
  await page.getByRole("button", { name: "More for Pasta" }).click();
  const pastaMenu = page.getByRole("menu", { name: "More for Pasta" });
  await pastaMenu.getByRole("menuitem", { name: "Already have it" }).click();
  await expect(pastaMenu).toBeHidden();
  const atHome = page.getByRole("region", { name: /^Already have/ });
  await expect(atHome.getByText("Pasta")).toBeVisible();

  // The pantry first, as in this person's shop.
  await page.getByRole("button", { name: "Aisle order" }).click();
  const order = page.getByRole("dialog", { name: "Aisle order" });
  for (let i = 0; i < 4; i++) {
    await order.getByRole("button", { name: "Move Pantry up" }).click();
  }
  const ordered = page.waitForResponse((r) => r.url().includes("/api/aisle-order"));
  await order.getByRole("button", { name: "Save" }).click();
  await ordered;

  await page.reload();
  const toGet = page.getByRole("region", { name: /^To get/ });
  await expect(toGet.getByRole("heading", { level: 3 }).first()).toHaveText("Pantry");
  await expect(page.getByRole("checkbox", { name: "Milk extra 2 L" })).toBeVisible();
  await expect(atHome.getByText("Pasta")).toBeVisible();

  // Next week: the usual is one click away.
  await page.getByRole("button", { name: "Next week" }).click();
  await page.getByRole("button", { name: "Add my usual" }).click();
  await expect(page.getByRole("checkbox", { name: "Milk extra 2 L" })).toBeVisible();
});
