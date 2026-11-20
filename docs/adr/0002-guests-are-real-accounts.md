# 0002: A first visit is a real, if anonymous, account

## Context

A portfolio project is judged in the first thirty seconds, often by
someone who will not sign up. But data has to belong to someone (0001), and
a separate "demo mode" with its own storage would be a second app to keep
correct.

## Decision

A first visit starts a **guest account**: a real `users` row with no email
or password, behind the same session cookie a signed-in user gets, seeded
with a few meals planned this week. Signing up attaches credentials to that
same row, so nothing moves and nothing is lost. Concurrent first requests
share one guest start (`web/src/api/client.ts`), and a session that ends
mid-use starts a fresh guest and says so, without replaying a write into it.

## Alternatives rejected

- **Sign-up wall.** Most visitors would never see the app.
- **Browser-only demo data.** Two storage paths, and signing up would need a
  migration from local storage to the server.

## Consequences

- One code path for everyone: guests exercise the same API, row security
  and tests as accounts.
- Guests cost database rows, so they are capped (30 new guests per network
  per hour) and a nightly job deletes any unused for 30 days, with
  everything they made.
