/// <reference lib="dom" />
/**
 * The security headers, as a browser receives them. The page's come from
 * vercel.json (served here by vite preview, as by Vercel in production); the
 * API's are set by the app itself.
 */

import { expect, test } from "./fixtures.ts";

test("the page arrives with its security headers", async ({ page }) => {
  const response = await page.goto("/");
  const headers = response!.headers();

  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  // And the app works under them: fonts, styles and the API all load (any
  // violation would fail this test, as it would every other).
  await expect(page.getByRole("region", { name: "The week" })).toBeVisible();
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("This week");
  expect(await page.evaluate(() => document.fonts.check("16px 'Fraunces Variable'"))).toBe(true);
});

test("the API's responses carry the API's stricter headers", async ({ page }) => {
  await page.goto("/");
  const response = await page.request.get("/api/state");
  const headers = response.headers();

  expect(headers["content-security-policy"]).toBe("default-src 'none'; frame-ancestors 'none'");
  expect(headers["cache-control"]).toBe("no-store");
  expect(headers["x-content-type-options"]).toBe("nosniff");
});

test.describe("an injected script", () => {
  test.use({ cspViolationsAllowed: true });

  test("is refused: the policy is enforced, not only sent", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("region", { name: "The week" })).toBeVisible();

    const ran = await page.evaluate(() => {
      const script = document.createElement("script");
      script.textContent = "window.__injected = true";
      document.head.append(script);
      return (window as { __injected?: boolean }).__injected === true;
    });

    expect(ran).toBe(false);
  });
});
