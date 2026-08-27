"""Wiring between the Streamlit UI and the data layer.

Streamlit re-runs the whole script on every interaction, so the engine is
cached to avoid rebuilding a connection pool each time while the cheap
repository wrappers are simply rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from app.db import DATABASE_URL_ENV_VAR, Database, load_env_file
from app.migrations import upgrade_to_head
from app.repositories import IngredientRepository, MealRepository, WeeklyPlanRepository


@dataclass(frozen=True, slots=True)
class Services:
    """Everything a tab needs to read or change data."""

    db: Database
    meals: MealRepository
    ingredients: IngredientRepository
    plans: WeeklyPlanRepository


def _configured_url() -> str | None:
    """The database URL from Streamlit secrets, if one is set there.

    Streamlit Community Cloud injects secrets rather than environment
    variables, so it is checked first. Returning None lets Database fall
    back to MEAL_PLANNER_DB_URL and then to local SQLite.
    """
    try:
        return st.secrets[DATABASE_URL_ENV_VAR]
    except Exception:
        # Raises rather than returning empty when no secrets file exists,
        # which is the normal case for local development.
        return None


@st.cache_resource
def _get_database() -> Database:
    """Build the engine once per server process, with the schema up to date.

    Cached because this runs the migrations: without it every widget
    interaction would re-check the schema over the network.
    """
    load_env_file()
    db = Database(_configured_url())
    upgrade_to_head(db.url)
    return db


def get_services() -> Services:
    """Assemble the repositories for this script run."""
    db = _get_database()
    return Services(
        db=db,
        meals=MealRepository(db),
        ingredients=IngredientRepository(db),
        plans=WeeklyPlanRepository(db),
    )
