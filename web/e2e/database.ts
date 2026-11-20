/**
 * The end-to-end API's database, and the one thing the harness does to it
 * directly.
 */

import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

// Not under test-results/, which Playwright empties when a run starts.
export const E2E_DATABASE = fileURLToPath(new URL("../.e2e/e2e.db", import.meta.url));

/**
 * Let the next test start a guest session, however many came before it.
 *
 * Each test is a new visitor, and a first visit starts a guest session. The
 * server allows 30 of those an hour from one network (app/ratelimit.py),
 * and every test comes from 127.0.0.1, so a suite of more than about 30
 * tests would find the door shut part-way through. Clearing that one count
 * between tests keeps the limit exactly as production has it, rather than
 * loosening it with a switch only tests should ever flip.
 */
export function resetGuestAllowance() {
  const db = new DatabaseSync(E2E_DATABASE);
  try {
    // The API may be writing at that moment; wait for it rather than fail.
    db.exec("PRAGMA busy_timeout = 5000");
    db.prepare("DELETE FROM rate_limits WHERE scope = ?").run("guest-network");
  } finally {
    db.close();
  }
}
