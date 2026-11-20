# 0006: Cold starts answered in the browser, not by keeping servers awake

## Context

On free tiers, after a quiet spell the serverless function has to start and
the Neon database has suspended (after five idle minutes). Measured: a
database wake-up of 0.45 s median and up to 2.2 s, plus about 0.6 s to
import the app. The first visit of the day sat on "Loading…" for one to
three seconds.

## Decision

1. The browser keeps a copy of the query cache (`web/src/api/persistence.ts`)
   and restores it before the first paint; the same single request then
   fetches the real data. Until it lands the page is inert, with
   "Updating…": the plan saves a whole week at a time, so an edit to an old
   copy could overwrite changes made since on another device.
2. A first visit shows a skeleton of the page, and after 2.5 s says the
   server is waking up.
3. Modules a cold start never uses (Alembic, the jobs, httpx) are imported
   on first use; a test fails if one creeps back.

## Alternatives rejected

- **A keep-warm ping.** Tried: scheduled every five minutes, GitHub ran it
  about every eight hours. And a database kept awake all day would use more
  compute than the free plan allows.
- **A paid tier.** Fixes the database, costs money every month, and still
  leaves the function's start.

## Consequences

- Return visits render instantly; when the server cannot be reached at all,
  the last copy stays readable (a shopping list in a shop with no signal).
- The browser now holds a copy of the user's data: it is versioned by a hash
  of the API's generated types, ignored after two weeks, cleared on logout,
  login and account deletion, and stated on the privacy page.
- Each cold start logs its import time, so the real figure is in the logs.
