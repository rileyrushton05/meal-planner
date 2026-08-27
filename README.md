# Meal Planner

[![Tests](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml/badge.svg)](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml)

A lightweight weekly meal planning app built with **Streamlit** and **SQLModel**. Add meals, attach ingredients with quantities, assign meals to days of the week, and automatically generate a consolidated grocery list for the week.

## Live demo

[**meal-planner-riley.streamlit.app**](https://meal-planner-riley.streamlit.app/) — hosted free on Streamlit Community Cloud. Free-tier apps sleep after 12 hours with no traffic; if you land on a "wake up" screen, click through it and the app restarts within a few seconds. Data resets on each cold start, since the free tier's filesystem isn't persistent — this is a UI demo, not a place to keep a real meal plan long-term.

## Features

- **Meal management** — create meals with a name and serving size, edit or delete them at any time. Deleting a meal asks for confirmation first, since it also removes its ingredient links and unassigns it from any planned day.
- **Ingredient tracking** — attach ingredients to a meal with a quantity (must be greater than 0) and unit (g, ml, tbsp, etc. — optional, for count-based items like "1 onion"), edit or remove them individually. Adding the same ingredient to a meal again accumulates the quantity rather than duplicating it. Meal and ingredient names match case-insensitively, so "Eggs" and "eggs" are treated as the same thing rather than silently fragmenting into duplicates. A search box lets you pick an ingredient you've already used, or a separate field lets you type a brand new one.
- **Quick-add meal templates** — a gallery of ~18 common meals (Spaghetti Bolognese, Tacos, Fried Rice, etc.) with typical ingredients already filled in, so staples don't have to be built from scratch every time.
- **Weekly scheduling** — assign a meal (and, optionally, how many servings you're actually cooking) to each day of the week via a simple form, shown as a color-coded day-by-day view. Pick any week with the week selector — each week's plan is independent, so past and future weeks are never overwritten.
- **Grocery list generation** — walks the selected week's assigned meals, pulls every linked ingredient, and merges quantities across meals that share the same ingredient and unit into a single shopping list. Metric mass and volume units (mg/g/kg, ml/L) are converted to a common base unit before merging, so "200 g" and "0.5 kg" of the same ingredient combine into one line instead of two. Ingredient quantities scale automatically if a day's planned servings differ from the meal's base recipe size. The list can be copied from a text box or downloaded as a `.txt` file.

## Tech stack

- **[Streamlit](https://streamlit.io/)** — the web UI, run directly from a Python script.
- **[SQLModel](https://sqlmodel.tiangolo.com/)** — ORM layer combining SQLAlchemy and Pydantic for the data models and queries.
- **[Postgres](https://www.postgresql.org/) (hosted on [Neon](https://neon.tech/))** in deployment; **SQLite** locally, with no code difference between them.
- **[Alembic](https://alembic.sqlalchemy.org/)** — versioned schema migrations, applied automatically at startup.
- **[streamlit-searchbox](https://github.com/m-wrzr/streamlit-searchbox)** — a custom Streamlit component providing the live-search picker for reusing an existing ingredient.

## Architecture

The app is split into a data layer that knows nothing about Streamlit, and a
presentation layer that knows nothing about SQL.

```
ui/  →  Services (repositories)  →  Database  →  SQLite or Postgres
```

Nothing above `Database` knows which backend is in use. Swapping SQLite for
Neon Postgres is a change of one environment variable — no repository,
planner or UI code refers to a specific database.

- **`app/`** owns the domain. `Database` holds the engine and hands out
  transactional sessions; the repositories in `repositories.py` run each
  operation inside one, so multi-step writes (a meal *and* all its
  ingredients) either land completely or roll back.
- **`ui/`** renders and nothing else. It receives repositories through
  `Services` rather than importing a global connection, which is what lets
  the tests point the whole app at a temporary database without patching
  any module internals.

```
meal-planner/
├── app/
│   ├── db.py            # Database: owns the engine, yields transactional sessions
│   ├── models.py        # SQLModel tables + the DayOfWeek enum
│   ├── repositories.py  # MealRepository / IngredientRepository / WeeklyPlanRepository
│   ├── planner.py       # GroceryItem + weekly grocery aggregation
│   ├── units.py         # Unit conversion and quantity formatting
│   ├── templates.py     # Starter meals for the Quick Add gallery
│   ├── migrations.py    # Applies Alembic migrations from Python at startup
│   └── exceptions.py    # Domain errors carrying user-facing messages
├── ui/
│   ├── streamlit_app.py # Entry point: page setup, week selector, tab routing
│   ├── services.py      # Builds the Database and repositories for a script run
│   ├── styles.py        # Theme tokens and the CSS applying them
│   └── tabs/            # One module per tab: meals, weekly_plan, grocery
├── migrations/          # Alembic revision history
├── tests/               # pytest suite, run against both SQLite and Postgres
├── data/data.db         # Local SQLite file, created automatically on first run
├── init_db.py           # Create the schema without launching the UI
├── alembic.ini          # Migration config; the URL comes from the environment
├── pyproject.toml       # Packaging, dependencies and pytest configuration
└── requirements.txt     # Installs the project (Streamlit Cloud reads this)
```

## Data model

- **Meal** — `id`, `name`, `servings`, `created_at`.
- **Ingredient** — `id`, `name`. Shared across every meal that uses it.
- **MealIngredient** — join table pairing a `Meal` with an `Ingredient`, plus the `qty` and `unit` for that pairing (many-to-many with extra fields).
- **WeeklyPlan** — maps a `(week_start_date, day_of_week)` pair to a `meal_id` and an optional planned `servings` count, one row per day per week, so different weeks never overwrite each other.

## Database and migrations

The backend is chosen entirely by `MEAL_PLANNER_DB_URL`:

| Environment | Value | Result |
|---|---|---|
| Local development | unset | SQLite at `data/data.db` |
| Deployment | `postgresql+psycopg://…` | Neon Postgres |
| Tests | set per test by the fixtures | Temporary SQLite file, or `TEST_DATABASE_URL` |

Note the `postgresql+psycopg://` prefix — Neon hands you a URL starting
`postgresql://`, and SQLAlchemy needs the driver named explicitly. Copy
`.env.example` to `.env` to work against Postgres locally; `.env` is
gitignored and must never be committed.

Schema changes are versioned with Alembic and applied automatically when the
app starts, because Streamlit Community Cloud has no release phase to run
them in. To change the schema:

```bash
# edit app/models.py, then:
alembic revision --autogenerate -m "what changed"
alembic upgrade head          # applied automatically on next app start too
```

CI runs `alembic check` to fail the build if a model change ships without a
matching migration, and `alembic downgrade base` to prove each migration is
reversible.

## Setup

1. **Clone the repo and enter the directory:**
   ```bash
   git clone <repo-url>
   cd meal-planner
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # on Windows: venv\Scripts\activate
   ```

3. **Install the project and its test tooling:**
   ```bash
   pip install -e ".[dev]"
   ```
   Or, without a build step: `pip install -r requirements-dev.txt`.

   Streamlit Community Cloud installs from `requirements.txt` and runs the
   entry script directly rather than installing the project, so
   `ui/streamlit_app.py` puts the project root on `sys.path` itself. That
   makes the app work either way — installed or not.

## Running the app

Start the Streamlit app from the project root:

```bash
streamlit run ui/streamlit_app.py
```

This opens the app in your browser (typically at `http://localhost:8501`). The SQLite database is created and migrated automatically on first run at `data/data.db`.

## Deployment

Deployed on Streamlit Community Cloud from `main`, backed by Neon Postgres.
The only configuration is one secret, set in **Manage app → Settings →
Secrets**:

```toml
MEAL_PLANNER_DB_URL = "postgresql+psycopg://user:password@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require"
```

Use Neon's *pooled* connection string (the host contains `-pooler`), since
the app opens connections from a long-lived process. Migrations run on
startup, so a deploy that changes the schema needs no manual step.

Unlike the previous SQLite-on-ephemeral-disk setup, data now survives
redeploys and the free tier's sleep cycle.

## Running tests

```bash
pytest
```

The suite runs against a temporary SQLite database created per test, never `data/data.db`.

## Usage

A week selector at the top applies to the Weekly Plan and Grocery List tabs — pick any date and it navigates to that date's Monday–Sunday week. The app is organized into three tabs:

1. **Meals** — add a meal by name, or one-click a starter from "Quick Add from Templates." Edit or delete meals (delete asks for confirmation), and attach ingredients (with quantity and unit) to a selected meal — search for an ingredient you've used before, or type a new one in the field beside it. Individual ingredients can be edited or removed without deleting the whole meal.
2. **Weekly Plan** — assign a meal and its planned servings to each day of the selected week (or leave a day unset) and save the plan; the week is shown as a color-coded card per day. Switching weeks doesn't lose any other week's plan. "Copy previous week's plan" carries the prior week's assignments forward instead of re-picking all 7 days from scratch.
3. **Grocery List** — generate a combined shopping list from everything assigned that week, with quantities merged across meals that share the same ingredient/unit and scaled for each day's planned servings. Copy it from the text box or download it as a `.txt` file.

