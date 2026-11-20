# 0001: Every query scoped in code, and again by Postgres row-level security

## Context

The app began single-user: one global list of meals and ingredients. Adding
accounts meant every table gained an owner, and every query an owner
filter. One forgotten `WHERE user_id = …` in a new endpoint would show one
person's meals to everyone, and code review is the only thing standing
between that bug and production.

## Decision

Two independent walls.

1. **In code:** a repository is constructed for one user
   (`app/repositories.py`, `_Repository(session, user_id=…)`) and has no
   method that takes a user per call, so no query can be written unscoped.
   Someone else's row answers 404, never 403, so ids reveal nothing.
2. **In the database:** the deployed app connects as `meal_planner_app`, a
   role that is not the owner. Each request sets the user it acts for, and
   every user table has a policy `user_id = current_app_user_id()`. The
   shared ingredient catalogue is read-only to that role.

## Alternatives rejected

- **Filters in code alone.** Correct today, one mistake from a leak.
- **A schema or database per user.** Isolation for free, but migrations and
  connections multiply with every guest, on a free-tier database.

## Consequences

- A query that forgets its filter returns nothing of anyone else's.
- Tests must run as the restricted role to prove anything: `tests/test_rls.py`
  builds the schema with the migrations and drives the API connected as
  `meal_planner_app`, including against another user's ids.
- Every new table needs its policy and grants in its migration; deleting an
  account is checked against every table found from the models
  (`tests/test_account.py`), so a new one cannot be missed.
