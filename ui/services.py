"""Wiring between the Streamlit UI and the data layer.

Streamlit re-runs the whole script on every interaction, so the engine is
cached to avoid rebuilding a connection pool each time while the cheap
repository wrappers are simply rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from app.db import Database
from app.repositories import IngredientRepository, MealRepository, WeeklyPlanRepository


@dataclass(frozen=True, slots=True)
class Services:
    """Everything a tab needs to read or change data."""

    db: Database
    meals: MealRepository
    ingredients: IngredientRepository
    plans: WeeklyPlanRepository


@st.cache_resource
def _get_database() -> Database:
    """Build the engine once per server process and ensure tables exist."""
    db = Database()
    db.create_tables()
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
