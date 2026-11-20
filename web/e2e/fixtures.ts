/**
 * Playwright's `test`, with one addition every spec gets: the page runs
 * under production's Content-Security-Policy (vite preview serves
 * vercel.json's headers), and any violation of it fails the test.
 *
 * A violation means something the app needs would be blocked in production:
 * a font, a style, a request. Catching it here, in every flow, beats finding
 * a blank page after a deploy.
 *
 * Covers the `page` fixture. A spec that opens its own browser contexts
 * (two visitors at once) checks those pages with `watchForCspViolations`.
 */

import { expect, type Page, test as base } from "@playwright/test";

import { resetGuestAllowance } from "./database.ts";

export function watchForCspViolations(page: Page): string[] {
  const violations: string[] = [];
  // The browser's own report, which names the blocked resource.
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) {
      violations.push(message.text());
    }
  });
  return violations;
}

export const test = base.extend<{
  cspViolationsAllowed: boolean;
  cspGuard: void;
  guestAllowance: void;
}>({
  /** Every test may start a guest session; see `resetGuestAllowance`. */
  guestAllowance: [
    // Playwright reads a fixture's dependencies from this pattern, so it
    // must be one even when, as here, there are none.
    // oxlint-disable-next-line no-empty-pattern
    async ({}, use) => {
      resetGuestAllowance();
      await use();
    },
    { auto: true },
  ],
  /** For the one test that breaks the policy on purpose, to prove it holds. */
  cspViolationsAllowed: [false, { option: true }],
  cspGuard: [
    async ({ page, cspViolationsAllowed }, use) => {
      const violations = watchForCspViolations(page);
      await use();
      if (!cspViolationsAllowed) {
        expect(violations, "Content-Security-Policy violations").toEqual([]);
      }
    },
    { auto: true },
  ],
});

export { expect };
