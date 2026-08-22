# Meal Planner

[![Tests](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml/badge.svg)](https://github.com/rileyrushton05/meal-planner/actions/workflows/tests.yml)

A lightweight weekly meal planning app built with **Streamlit** and **SQLModel**. Add meals, attach ingredients with quantities, assign meals to days of the week, and automatically generate a consolidated grocery list for the week.

## Live demo

[**meal-planner-riley.streamlit.app**](https://meal-planner-riley.streamlit.app/) — hosted free on Streamlit Community Cloud. Free-tier apps sleep after 12 hours with no traffic; if you land on a "wake up" screen, click through it and the app restarts within a few seconds. Data resets on each cold start, since the free tier's filesystem isn't persistent — this is a UI demo, not a place to keep a real meal plan long-term.

## Features

- **Meal management** — create meals with a name and serving size, edit or delete them at any time. Deleting a meal asks for confirmation first, since it also removes its ingredient links and unassigns it from any planned day.
- **Ingredient tracking** — attach ingredients to a meal with a quantity and unit (g, ml, tbsp, etc.), edit or remove them individually. Adding the same ingredient to a meal again accumulates the quantity rather than duplicating it. Meal and ingredient names match case-insensitively, so "Eggs" and "eggs" are treated as the same thing rather than silently fragmenting into duplicates. A search box lets you pick an ingredient you've already used, or a separate field lets you type a brand new one.
- **Quick-add meal templates** — a gallery of ~18 common meals (Spaghetti Bolognese, Tacos, Fried Rice, etc.) with typical ingredients already filled in, so staples don't have to be built from scratch every time.
- **Weekly scheduling** — assign a meal (and, optionally, how many servings you're actually cooking) to each day of the week via a simple form, shown as a color-coded day-by-day view. Pick any week with the week selector — each week's plan is independent, so past and future weeks are never overwritten.
- **Grocery list generation** — walks the selected week's assigned meals, pulls every linked ingredient, and merges quantities across meals that share the same ingredient and unit into a single shopping list. Metric mass and volume units (mg/g/kg, ml/L) are converted to a common base unit before merging, so "200 g" and "0.5 kg" of the same ingredient combine into one line instead of two. Ingredient quantities scale automatically if a day's planned servings differ from the meal's base recipe size. The list can be copied from a text box or downloaded as a `.txt` file.

## Tech stack

- **[Streamlit](https://streamlit.io/)** — the web UI, run directly from a Python script.
- **[SQLModel](https://sqlmodel.tiangolo.com/)** — ORM layer combining SQLAlchemy and Pydantic for the data models and queries.
- **SQLite** — file-based database (via Python's built-in `sqlite3`), stored at `data/data.db`.
- **[streamlit-searchbox](https://github.com/m-wrzr/streamlit-searchbox)** — a custom Streamlit component providing the live-search picker for reusing an existing ingredient.

## Project structure

```
meal-planner/
├── app/
│   ├── db.py         # SQLite engine/session setup, table creation
│   ├── models.py     # SQLModel table definitions (Meal, Ingredient, MealIngredient, WeeklyPlan)
│   ├── crud.py        # Create/read/delete helpers for meals, ingredients, and the weekly plan
│   ├── planner.py     # Aggregates the week's meals into a merged grocery list
│   └── templates.py   # Starter meal data for the Quick Add gallery
├── ui/
│   └── streamlit_app.py  # Streamlit front end — wires the UI to the CRUD/planner functions
├── .streamlit/
│   └── config.toml      # Dark color theme (background, accent, fonts)
├── data/
│   └── data.db         # SQLite database file (created automatically on first run)
├── tests/               # pytest suite for crud.py and planner.py, isolated from data/data.db
├── init_db.py          # Standalone script to create the database and tables
├── requirements.txt
├── requirements-dev.txt # Adds pytest for running the test suite
└── README.md
```

## Data model

- **Meal** — `id`, `name`, `servings`, `created_at`.
- **Ingredient** — `id`, `name`.
- **MealIngredient** — join table linking a `Meal` to an `Ingredient`, with a `qty` and `unit` for that pairing (many-to-many with extra fields).
- **WeeklyPlan** — maps a `(week_start_date, day_of_week)` pair to a `meal_id` and an optional planned `servings` count, one row per day per week, so different weeks never overwrite each other.

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

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the app

Start the Streamlit app from the project root:

```bash
streamlit run ui/streamlit_app.py
```

This opens the app in your browser (typically at `http://localhost:8501`). The SQLite database and tables are created automatically on first run at `data/data.db`.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs against a temporary SQLite database created per test, never `data/data.db`.

## Usage

A week selector at the top applies to the Weekly Plan and Grocery List tabs — pick any date and it navigates to that date's Monday–Sunday week. The app is organized into three tabs:

1. **Meals** — add a meal by name, or one-click a starter from "Quick Add from Templates." Edit or delete meals (delete asks for confirmation), and attach ingredients (with quantity and unit) to a selected meal — search for an ingredient you've used before, or type a new one in the field beside it. Individual ingredients can be edited or removed without deleting the whole meal.
2. **Weekly Plan** — assign a meal and its planned servings to each day of the selected week (or leave a day unset) and save the plan; the week is shown as a color-coded card per day. Switching weeks doesn't lose any other week's plan. "Copy previous week's plan" carries the prior week's assignments forward instead of re-picking all 7 days from scratch.
3. **Grocery List** — generate a combined shopping list from everything assigned that week, with quantities merged across meals that share the same ingredient/unit and scaled for each day's planned servings. Copy it from the text box or download it as a `.txt` file.

