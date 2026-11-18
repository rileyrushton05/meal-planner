# Meal Planner

[![Tests](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml/badge.svg)](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml)

Plan a week of meals and get a consolidated grocery list. A React frontend
over a FastAPI backend, backed by Postgres.

## Live demo

[**meal-planner-liard-ten.vercel.app**](https://meal-planner-liard-ten.vercel.app/)
— frontend and API deployed together on Vercel, with the database on Neon.

## Features

- **Start straight away** — a first visit opens as a guest with three sample meals planned on four days of the current week, so the grocery list has something to show. Signing up keeps everything; logging in on another device brings it back.
- **Meals** — create meals with a serving size, edit or delete them (deleting asks for confirmation, since it also removes ingredients and unassigns planned days).
- **Ingredients** — attach quantities and units, with autocomplete over ingredients already used. Names match case-insensitively, so "Eggs" and "eggs" stay one item rather than splitting the shopping list.
- **Quick-add templates** — ~18 common meals with typical ingredients already filled in.
- **Weekly plan** — assign a meal and serving count to each day of any week. Weeks are independent, so planning ahead never overwrites the current one, and "copy previous week" carries assignments forward.
- **Grocery list** — totals everything planned for a week. Metric mass and volume (mg/g/kg, ml/L) convert to a common unit before merging, and quantities scale when a day's servings differ from the recipe. Copy it or download it as `.txt`.

## Architecture

Three layers, each ignorant of the ones around it:

```
web/ (React)  →  server/ (FastAPI)  →  app/ (domain)  →  Postgres / SQLite
```

- **`app/`** owns the domain and knows nothing about HTTP. `Database` holds the
  engine and opens transactions; the repositories work inside whichever one
  they are handed and never commit, so each API request lands completely or
  rolls back as a whole, and the commit finishes before the response is sent.
- **`server/`** translates HTTP to repository calls and contains no SQL. Domain
  errors map to status codes and RFC 9457 problem responses, so messages
  written for users surface verbatim.
- **`web/`** renders, and holds server state in TanStack Query. It loads a
  week in a single request and works from memory afterwards: mutations patch
  the cache from the API's response rather than refetching. Each page has
  its own address (`/meals`, `/plan`, `/groceries`) and the week is in the
  query string, so a refresh, the back button or a shared link opens the same
  view. Light, dark and match-device themes, with the choice applied before
  first paint. Built on shadcn/ui over Base UI primitives, so dialogs and
  selects are accessible without hand-rolling them.

Nothing above `Database` knows which backend is in use — swapping SQLite for
Postgres is one environment variable.

### Accounts

Everyone has an account. A first visit starts a **guest** account (no email,
no password) behind a session cookie, so the planner works immediately;
signing up attaches credentials to that same account, keeping everything the
guest made. Repositories are constructed for one user, so no query can run
unscoped, and someone else's meal answers 404, never 403.

- **Passwords:** argon2id (RFC 9106 parameters, upgraded at login if they
  change), length 8–128, and the 10,000 most common breached passwords are
  refused. No composition rules, per NIST SP 800-63B.
- **Sessions:** a random 256-bit token in an `HttpOnly`, `Secure`,
  `SameSite=Strict`, `__Host-` cookie. The database stores only its SHA-256,
  so a leaked table cannot be replayed. Sessions end after 30 days without a
  visit, and the token is replaced at login and signup (session fixation).
- **Login** answers identically, in identical time, whether the email is
  unknown or the password is wrong.
- **Cross-site requests:** besides `SameSite=Strict`, any write whose
  `Origin` (or `Sec-Fetch-Site`) says another website sent it is refused.
- **Throttling:** five wrong passwords for one account from one network
  start a wait (1 minute, doubling to 15) during which even the right
  password is refused; a higher ceiling per account catches guesses spread
  across many networks without letting one attacker lock the owner out.
  Guest sessions and "email already taken" answers are capped per network
  per hour. Emails and IP addresses are stored only as keyed hashes, and
  the address comes from the platform's header, never one a client can set.
- **Security events:** signups, logins, failures, throttling and refused
  cross-site requests are logged as JSON with the request id; passwords,
  tokens, emails and IP addresses never are, and a test checks the logs.
- **Row-level security:** in Postgres, the app connects as a role that can
  only see and write rows belonging to the user its request declared.
  Repositories filter by user, and the database filters again, so a query
  that forgot its filter still returns nothing of anyone else's.
  ([database-schema.md](docs/database-schema.md#row-level-security-postgres))
- **Security headers:** the web page runs under a Content-Security-Policy
  that allows only its own scripts, styles, fonts and API (nothing inline,
  nothing from another host) and cannot be framed. Vercel's CDN serves the
  page, so its headers live in `vercel.json`; the preview server the
  end-to-end tests use reads them from there, and every Playwright test fails
  on any violation. API responses get a stricter set from the app itself
  (`server/headers.py`): no content allowed at all, `no-store`, `nosniff`.
- **Recovery codes, not email:** a forgotten password is reset with a
  recovery code shown once at signup (16 characters, 80 random bits),
  rather than an emailed link. The app never sends email, so no third
  party ever receives users' addresses, and there is no provider to depend
  on. Only the code's SHA-256 is stored; each code works once (recovery
  issues the next); resetting ends every session; the refusal is the same
  whether the email or the code is wrong, and guesses share login's
  throttle. Codes can be replaced from the Account page with the password.
  The trade-off: lose both the password and the code, and the account is
  gone (an operator can still use `set-password`).
- **Leaving:** the Account page downloads everything that is yours as
  readable JSON (meals, ingredients, every planned day; names rather than
  internal ids, and never a password hash or token), and deletes the
  account in one statement that cascades to every row it owns, ending every
  session. An account confirms with its password, throttled together with
  login so a stolen session cannot use it to guess; a guest needs nothing.
  Tests check that deletion leaves no row of the account's in any table
  (found from the models, so a new table is covered) and touches no one
  else's, including as the app's restricted role under row security.
- **Tests:** every API route is checked, from the OpenAPI document, to
  answer 401 without a session, so a new route cannot ship open. The row
  security tests run connected as the app's own role, against a schema
  built by the migrations.

### Latency

Most of the design here is a response to one measurement: a round trip to a
database on another continent cost **325 ms**, so what mattered was the number
of round trips, not the speed of any query.

| | Before | After |
|---|---|---|
| Grocery list for a week | 48 queries | 1 |
| Saving a week's plan | 14 statements | 2 |
| One HTTP request | up to 4 transactions | 1 |
| Changing week | 3.4 s | 0.11 s |

Four changes, in order of how much they bought:

1. **Colocation.** Functions run in `syd1`, next to the `ap-southeast-2`
   database and the person using it. Previously the request crossed the
   Pacific twice. A round trip fell from 325 ms to 41 ms.
2. **Fetch only what changed.** Meals, templates and ingredient names do not
   vary by week, so changing week asks for the plan alone. Weeks already
   visited are served from memory and issue no request at all.
3. **One transaction per request.** Each repository used to open its own
   session, so a request touching three of them paid three BEGIN/COMMIT
   pairs — 1.5 s of the original 3.4 s was transaction overhead alone.
4. **One query, not N.** The grocery list is a single four-table join rather
   than a query per meal and per ingredient.

The frontend loads a week in one request and works from memory afterwards, so
changing page or opening a dropdown touches no network at all. Only changes
hit the API.

```
meal-planner/
├── app/                  # Domain layer
│   ├── db.py             #   Database: owns the engine, opens the one transaction per request
│   ├── models.py         #   SQLModel tables + the DayOfWeek enum
│   ├── repositories.py   #   Meal / Ingredient / WeeklyPlan repositories
│   ├── planner.py        #   GroceryItem + weekly aggregation
│   ├── units.py          #   Unit conversion and quantity formatting
│   ├── templates.py      #   Starter meals
│   ├── migrations.py     #   Applies Alembic migrations from Python
│   └── exceptions.py     #   Domain errors carrying user-facing messages
├── server/               # FastAPI application
│   ├── main.py           #   App setup, CORS, middleware order
│   ├── deps.py           #   Database and repository wiring
│   ├── problems.py       #   RFC 9457 error responses
│   ├── observability.py  #   Request ids and structured logs
│   ├── schemas.py        #   Request/response models
│   ├── serializers.py    #   Domain objects → response models
│   └── routers/          #   meals, plans, state, health
├── api/index.py          # Vercel serverless entry point
├── web/                  # React + TypeScript + Tailwind frontend
│   └── src/
│       ├── api/          #   Typed client and shared types
│       ├── components/   #   The three views; ui/ holds shadcn primitives
│       ├── hooks/        #   usePlanner: server state via TanStack Query
│       └── lib/          #   Week arithmetic
├── migrations/           # Alembic revision history
├── tests/                # Python suite, run against SQLite and Postgres
├── alembic.ini
├── pyproject.toml
└── vercel.json
```

## Data model

Everything a person creates belongs to one row in `users`: their `meals`,
their `ingredients` (each person's own, so the autocomplete never suggests a
stranger's), the `meal_ingredients` pairing them with quantities, and their
`weekly_plans`, one row per day per week. Names are unique per person
ignoring case, quantities and servings are positive, and days are weekdays,
all enforced by the database rather than only in Python.

The full schema, an ER diagram, and what happens on delete are in
[docs/database-schema.md](docs/database-schema.md).

## Setup

```bash
git clone <repo-url> && cd meal-planner
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cd web && npm install && cd ..
```

The database is chosen entirely by `MEAL_PLANNER_DB_URL`:

| Environment | Value | Result |
|---|---|---|
| Local | unset | SQLite at `data/data.db` |
| Deployment | `postgresql+psycopg://…` | Neon Postgres |
| Tests | set per test | Temporary SQLite, or `TEST_DATABASE_URL` |

Note the `postgresql+psycopg://` prefix — Neon gives you a URL starting
`postgresql://`, and SQLAlchemy needs the driver named explicitly. Copy
`.env.example` to `.env` to point local development at Postgres; `.env` is
gitignored.

## Running it

Two processes. The Vite dev server proxies `/api` to the backend, so the
frontend uses the same relative URLs it will in production.

```bash
uvicorn server.main:app --reload --no-access-log --port 8000   # terminal 1
cd web && npm run dev                          # terminal 2
```

The frontend runs on `http://localhost:5173`. Interactive API docs are at
`http://localhost:8000/docs`.

## Conventions

Errors are RFC 9457 Problem Details, request bodies reject unknown fields,
every response carries an `X-Request-ID` that appears in every log line for
that request, and `/health/ready` checks the database. The full set, and the
test that enforces each, is in [docs/conventions.md](docs/conventions.md).

## Tests

```bash
pytest               # Python: domain, repositories, API
ruff check . && ruff format --check .
cd web && npm test   # Frontend: components, client, date handling
cd web && npm run lint
cd web && npm run test:e2e   # Playwright: the built app in Chromium
```

Python tests run against SQLite by default and Postgres when
`TEST_DATABASE_URL` is set. Running both is what proves the data layer is
genuinely portable rather than accidentally SQLite-shaped — it caught a
handler returning 500 instead of 404, because SQLite does not enforce foreign
keys by default and Postgres does.

CI runs both legs, the frontend suite, `ruff` for lint and formatting, and two
migration checks: `alembic check` fails the build if a model change ships
without a migration, and a downgrade proves each migration is reversible.

The frontend's types are generated, not hand-written. The OpenAPI document is
exported to [`docs/openapi.json`](docs/openapi.json) and the TypeScript in
`web/src/api/schema.ts` is generated from it with `openapi-typescript`. A test
fails if the committed document no longer matches the API, and CI fails if the
generated TypeScript is stale, so a renamed field or a changed nullability
breaks the build rather than surfacing as `undefined` in the browser. After
changing a model or route:

```bash
python scripts/export_openapi.py
cd web && npm run generate:api
```

## Migrations

Schema changes are versioned with Alembic:

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

Migrations run automatically at startup for a long-lived local server, but
**never on Vercel**: every cold start would re-check the schema, and
concurrent functions could race. Production is migrated by the
[`Migrate production`](.github/workflows/migrate.yml) workflow, which runs
when a push to `main` changes `migrations/` and waits for approval through a
GitHub environment before touching the database. It refuses to run unless
its target is Postgres, so a missing secret cannot "succeed" against a
throwaway SQLite file.

**Migrate first, then deploy.** Merging to `main` starts the Vercel deploy
and the migration at the same moment, and the migration waits for approval.
Code that reads a new column fails on every request until that column
exists, so a migration the new code depends on is applied *before* merging:
from the branch, with the owner's URL, on the `preview` Neon branch first
(which preview deployments also need) and then on production. Migrations
are written additively so the code already running is unaffected. After the
merge, the workflow finds nothing left to do.

## Deployment

Vercel serves the frontend and the API from one origin, so there is no CORS
configuration and the client uses relative paths.

- **Framework preset:** Other (the build is defined in `vercel.json`)
- **Root directory:** the repository root
- **Environment variables** (Production scope):
  - `MEAL_PLANNER_DB_URL`: Neon's pooled URL for `meal_planner_app`, the
    role row-level security applies to, not the owner.
  - `MEAL_PLANNER_RATE_LIMIT_KEY`: a long random value; throttling hashes
    emails and addresses with it.
- **Migrations:** a GitHub environment named `production` with a required
  reviewer, holding `MEAL_PLANNER_MIGRATION_DB_URL` (the owner's direct,
  non-pooled URL). See [Migrations](#migrations).
- **Scheduled jobs:** a GitHub environment named `jobs`, limited to `main`
  and with no reviewer (it runs nightly), holding `MEAL_PLANNER_JOBS_DB_URL`
  (the owner's direct URL). `.github/workflows/jobs.yml` runs
  `python -m app.jobs purge-guests` at 3:17 a.m. Brisbane time: guests
  idle for 30 days go, with everything they made, along with expired
  sessions and stale rate-limit records. Run it by hand from the Actions
  tab as a dry run first.
- **Region:** `syd1`, set in `vercel.json`. Functions default to `iad1`
  (Virginia); running them next to the database is worth more than any
  application-level optimisation here.

`api/requirements.txt` sits next to the serverless entry point deliberately:
with a custom `buildCommand`, Vercel's Python builder does not pick up the
root file, and the function fails to import its dependencies.

### Claiming the data from before accounts

The accounts migration gave every existing meal and plan to one account
with no email or password, since a migration must not contain a secret.
After migrating, whoever deploys gives it a login, connected as the owner:

```bash
export MEAL_PLANNER_DB_URL='postgresql+psycopg://...'   # owner, direct URL
python3 scripts/db_report.py                             # check the host first
python3 -m app.cli claim-account
unset MEAL_PLANNER_DB_URL
```

It shows how many meals the account holds, asks for an email and a password
(twice, read without echoing and never printed), applies the same checks as
signing up, and changes nothing until you type `yes`.

### Replacing a forgotten password

Until password reset by email exists, the same owner connection can give an
account a new password:

```bash
python3 -m app.cli set-password
```

It asks for the account's email and the new password (twice, never printed),
applies the same password checks, and changes nothing until you type `yes`.
It then ends every session the account has, so any browser still signed in
with the old password is signed out.
