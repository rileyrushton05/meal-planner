# Meal Planner

[![Tests](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml/badge.svg)](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml)

Plan a week of meals and get a consolidated grocery list. A React frontend
over a FastAPI backend, backed by Postgres.

## Live demo

[**meal-planner-liard-ten.vercel.app**](https://meal-planner-liard-ten.vercel.app/)
— frontend and API deployed together on Vercel, with the database on Neon.

## Features

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
  engine and yields transactional sessions; the repositories run each operation
  inside one, so multi-step writes either land completely or roll back.
- **`server/`** translates HTTP to repository calls and contains no SQL. Domain
  errors map to status codes, so messages written for users surface verbatim.
- **`web/`** renders and holds state. It loads a week in a single request and
  works from memory afterwards.

Nothing above `Database` knows which backend is in use — swapping SQLite for
Postgres is one environment variable.

### Why a single `/api/state` endpoint

The app previously used Streamlit, which re-runs the whole script on every
interaction. Against a local SQLite file that was free; against a network
database each click cost roughly five round trips and about a second.

The current design loads everything for a week in one request and keeps it in
memory, so switching tabs or editing a dropdown touches no network at all.
Only changes hit the API.

```
meal-planner/
├── app/                  # Domain layer
│   ├── db.py             #   Database: owns the engine, yields transactional sessions
│   ├── models.py         #   SQLModel tables + the DayOfWeek enum
│   ├── repositories.py   #   Meal / Ingredient / WeeklyPlan repositories
│   ├── planner.py        #   GroceryItem + weekly aggregation
│   ├── units.py          #   Unit conversion and quantity formatting
│   ├── templates.py      #   Starter meals
│   ├── migrations.py     #   Applies Alembic migrations from Python
│   └── exceptions.py     #   Domain errors carrying user-facing messages
├── server/               # FastAPI application
│   ├── main.py           #   App setup, CORS, error mapping
│   ├── deps.py           #   Database and repository wiring
│   ├── schemas.py        #   Request/response models
│   ├── serializers.py    #   Domain objects → response models
│   └── routers/          #   meals, plans, state
├── api/index.py          # Vercel serverless entry point
├── web/                  # React + TypeScript + Tailwind frontend
│   └── src/
│       ├── api/          #   Typed client and shared types
│       ├── components/   #   Tabs and the three views
│       ├── hooks/        #   usePlanner: one week of state
│       └── lib/          #   Week arithmetic
├── migrations/           # Alembic revision history
├── tests/                # Python suite, run against SQLite and Postgres
├── alembic.ini
├── pyproject.toml
└── vercel.json
```

## Data model

- **Meal** — `id`, `name`, `servings`, `created_at`.
- **Ingredient** — `id`, `name`. Shared across every meal that uses it.
- **MealIngredient** — join table pairing a meal with an ingredient, plus the `qty` and `unit` for that pairing.
- **WeeklyPlan** — maps `(week_start_date, day_of_week)` to a `meal_id` and an optional planned `servings`, one row per day per week.

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
uvicorn server.main:app --reload --port 8000   # terminal 1
cd web && npm run dev                          # terminal 2
```

The frontend runs on `http://localhost:5173`. Interactive API docs are at
`http://localhost:8000/docs`.

## Tests

```bash
pytest          # Python: domain, repositories, API
cd web && npm test   # Frontend: components, client, date handling
```

Python tests run against SQLite by default and Postgres when
`TEST_DATABASE_URL` is set. CI runs both, plus the frontend suite, plus two
migration checks: `alembic check` fails the build if a model change ships
without a migration, and a downgrade proves each migration is reversible.

One test compares the TypeScript interfaces in `web/src/api/types.ts` against
the Pydantic schemas, so renaming a field on either side fails the build
rather than surfacing as `undefined` in the browser.

## Migrations

Schema changes are versioned with Alembic:

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

Migrations run automatically at startup for a long-lived server, but **not on
Vercel** — every cold start would re-check the schema, and concurrent
functions could race. Apply them manually or from CI after a schema change.

## Deployment

Vercel serves the frontend and the API from one origin, so there is no CORS
configuration and the client uses relative paths.

- **Framework preset:** Other (the build is defined in `vercel.json`)
- **Root directory:** the repository root
- **Environment variable:** `MEAL_PLANNER_DB_URL`, Production scope

`api/requirements.txt` sits next to the serverless entry point deliberately:
with a custom `buildCommand`, Vercel's Python builder does not pick up the
root file, and the function fails to import its dependencies.
