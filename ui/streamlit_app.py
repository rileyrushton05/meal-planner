"""Entry point for the Weekly Meal Planner.

Run with: streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# Streamlit runs this file as a script rather than importing it, so only
# ui/ lands on sys.path - not the project root that `app` and `ui` live in.
# Locally `pip install -e .` would cover it, but Streamlit Community Cloud
# installs requirements.txt without installing the project itself, so the
# root is added here. Harmless when the package is already installed.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st  # noqa: E402

from ui import styles  # noqa: E402
from ui.services import get_services  # noqa: E402
from ui.tabs import grocery, meals, weekly_plan  # noqa: E402


def _week_selector() -> date:
    """Pick a week, returning the Monday it starts on.

    Any date is accepted and snapped back to its Monday, so the user never
    has to know which day a week officially begins on.
    """
    today = date.today()
    default_monday = today - timedelta(days=today.weekday())

    picked = st.date_input("Week", value=default_monday, key="week_picker")
    monday = picked - timedelta(days=picked.weekday())
    sunday = monday + timedelta(days=6)

    st.caption(
        f"Viewing week of {monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
    )
    return monday


def main() -> None:
    st.set_page_config(page_title="Weekly Meal Planner", layout="wide")
    styles.inject_theme()

    st.title("Weekly Meal Planner")
    st.caption(
        "Plan your meals, build your week, and generate your grocery list "
        "— all in one place."
    )

    services = get_services()
    week_start = _week_selector()

    meals_tab, plan_tab, grocery_tab = st.tabs(
        ["Meals", "Weekly Plan", "Grocery List"]
    )
    with meals_tab:
        meals.render(services)
    with plan_tab:
        weekly_plan.render(services, week_start)
    with grocery_tab:
        grocery.render(services, week_start)


main()
