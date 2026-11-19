import { defineConfig } from "@playwright/test";

import e2e from "./playwright.config.ts";

/**
 * The README's screenshots, taken from the same production build and fresh
 * SQLite database as the end-to-end tests, so they show the real app and
 * never touch a deployed one. Not part of the test run:
 *
 *   npm run screenshots
 *
 * writes docs/images/*.png. Run it after a visible change and commit the
 * images with it.
 */
export default defineConfig({
  ...e2e,
  testDir: "screenshots",
  reporter: "list",
  projects: [{ name: "screenshots", use: { browserName: "chromium" } }],
});
