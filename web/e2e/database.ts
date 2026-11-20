/**
 * The end-to-end API's database, and the one thing the harness does to it
 * directly.
 */

import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

// Not under test-results/, which Playwright empties when a run starts.
export const E2E_DATABASE = fileURLToPath(new URL("../.e2e/e2e.db", import.meta.url));

/**
 * Let the next test start a guest session, or sign up, however many came
 * before it.
 *
 * Each test is a new visitor, and a first visit starts a guest session. The
 * server allows 30 of those an hour from one network, and caps signups per
 * network and new accounts overall (app/ratelimit.py). Every test comes
 * from 127.0.0.1, so a suite of more than about 30 tests would find the
 * door shut part-way through. Clearing those counts between tests keeps
 * the limits exactly as production has them, rather than loosening them
 * with a switch only tests should ever flip.
 */
export function resetGuestAllowance() {
  const db = new DatabaseSync(E2E_DATABASE);
  try {
    // The API may be writing at that moment; wait for it rather than fail.
    db.exec("PRAGMA busy_timeout = 5000");
    db.prepare("DELETE FROM rate_limits WHERE scope IN (?, ?, ?)").run(
      "guest-network",
      "signup-network",
      "new-accounts",
    );
  } finally {
    db.close();
  }
}
