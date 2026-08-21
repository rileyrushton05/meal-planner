# Meal Planner

A lightweight weekly meal planning app built with **Streamlit** and **SQLModel**. Add meals, attach ingredients with quantities, assign meals to days of the week, and automatically generate a consolidated grocery list for the week.

## Features

- **Meal management** — create meals with a name and serving size.
- **Ingredient tracking** — attach ingredients to a meal with a quantity and unit (g, ml, tbsp, etc.). Adding the same ingredient to a meal again accumulates the quantity rather than duplicating it.
- **Weekly scheduling** — assign one meal to each day of the week (Monday–Sunday) via a simple form.
- **Grocery list generation** — walks the week's assigned meals, pulls every linked ingredient, and merges quantities across meals that share the same ingredient and unit into a single shopping list.

## Tech stack

- **[Streamlit](https://streamlit.io/)** — the web UI, run directly from a Python script.
- **[SQLModel](https://sqlmodel.tiangolo.com/)** — ORM layer combining SQLAlchemy and Pydantic for the data models and queries.
- **SQLite** — file-based database (via Python's built-in `sqlite3`), stored at `data/data.db`.
- **[pandas](https://pandas.pydata.org/)** — used to shape query results into tables for display in the UI.

## Project structure

```
meal-planner/
├── app/
│   ├── db.py         # SQLite engine/session setup, table creation
│   ├── models.py     # SQLModel table definitions (Meal, Ingredient, MealIngredient, WeeklyPlan, GroceryItem)
│   ├── crud.py        # Create/read helpers for meals, ingredients, and the weekly plan
│   └── planner.py     # Aggregates the week's meals into a merged grocery list
├── ui/
│   └── streamlit_app.py  # Streamlit front end — wires the UI to the CRUD/planner functions
├── data/
│   └── data.db         # SQLite database file (created automatically on first run)
├── init_db.py          # Standalone script to create the database and tables
├── requirements.txt
└── README.md
```

## Data model

- **Meal** — `id`, `name`, `servings`, `created_at`.
- **Ingredient** — `id`, `name`.
- **MealIngredient** — join table linking a `Meal` to an `Ingredient`, with a `qty` and `unit` for that pairing (many-to-many with extra fields).
- **WeeklyPlan** — maps a `day_of_week` to a `meal_id`, one row per day.
- **GroceryItem** — standalone model for a shopping list entry (`name`, `desired_qty`, `unit`, `bought`), separate from the generated weekly grocery list.

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

## Usage

1. **Add Meal** — enter a name and click "Add Meal".
2. **Add Ingredient to Meal** — pick a meal, then enter an ingredient name, quantity, and unit.
3. **Assign Meals to Days** — select a meal for each day of the week and submit the form.
4. **Weekly Schedule** — view the current day-to-meal assignments in a table.
5. **Generate Grocery List** — click the button to compute and display the combined ingredient list for everything scheduled that week.

