"""Shared fixtures.

Every test runs against its own throwaway SQLite file. Isolation comes from
constructing :class:`~app.db.Database` with an explicit URL, plus setting the
same URL in the environment so code that builds its own Database (the
Streamlit UI) picks it up too. Nothing patches module internals.
"""

from __future__ import annotations

import pytest
import streamlit as st

from app.db import DATABASE_URL_ENV_VAR, Database
from app.repositories import (
    IngredientRepository,
    MealRepository,
    WeeklyPlanRepository,
)


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch) -> Database:
    """A Database backed by a temporary file, never data/data.db."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, url)

    # The UI caches its Database in st.cache_resource, which would otherwise
    # leak one test's data into the next.
    st.cache_resource.clear()

    database = Database(url)
    database.create_tables()
    yield database

    st.cache_resource.clear()


@pytest.fixture
def meals(db: Database) -> MealRepository:
    return MealRepository(db)


@pytest.fixture
def ingredients(db: Database) -> IngredientRepository:
    return IngredientRepository(db)


@pytest.fixture
def plans(db: Database) -> WeeklyPlanRepository:
    return WeeklyPlanRepository(db)
