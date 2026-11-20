import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

import { E2E_DATABASE as database } from "./e2e/database.ts";

/**
 * End-to-end tests: the production build in a real browser, against the real
 * API on a fresh SQLite database.
 *
 * Both servers run on their own ports, so a development server already
 * running on 5173/8000 is never reused or disturbed. The database file is
 * deleted before the API starts, so every run begins empty; the specs avoid
 * depending on each other by working in different weeks and using their own
 * meal names.
 */

const API_PORT = 8001;
const WEB_PORT = 4174;
/** Serves e2e/pages/, standing in for a recipe website to import from. */
const RECIPE_SITE_PORT = 4175;
const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  testDir: "e2e",
  // One shared database, so specs run one at a time.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `mkdir -p "$(dirname "${database}")" && rm -f "${database}" && python3 -m uvicorn server.main:app --port ${API_PORT} --no-access-log`,
      cwd: repoRoot,
      url: `http://127.0.0.1:${API_PORT}/health/ready`,
      env: {
        MEAL_PLANNER_DB_URL: `sqlite:///${database}`,
        // The preview server's proxy rewrites Host, so the page's Origin has
        // to be named as trusted for writes to pass the cross-site check.
        MEAL_PLANNER_CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        // Recipe import refuses local addresses; this one origin, the
        // fixture site below, is exempt. Ignored on Vercel (app/importing.py).
        MEAL_PLANNER_IMPORT_UNCHECKED_ORIGIN: `http://127.0.0.1:${RECIPE_SITE_PORT}`,
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npm run build && npx vite preview --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `python3 -m http.server ${RECIPE_SITE_PORT} --bind 127.0.0.1 --directory e2e/pages`,
      url: `http://127.0.0.1:${RECIPE_SITE_PORT}/ragu.html`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
