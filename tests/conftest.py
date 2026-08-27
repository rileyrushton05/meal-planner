"""Shared fixtures.

Tests run against SQLite by default: a fresh temporary file per test, no
server required. Setting TEST_DATABASE_URL points the same suite at Postgres
instead, which is how CI proves the code is genuinely portable rather than
accidentally SQLite-shaped.

Isolation comes from constructing :class:`~app.db.Database` with an explicit
URL, and from setting that URL in the environment so code building its own
Database (the Streamlit UI) picks it up too. Nothing patches module
internals.
"""

from __future__ import annotations

import os

import pytest
import streamlit as st
from sqlmodel import SQLModel

from app.db import DATABASE_URL_ENV_VAR, Database
from app.migrations import stamp_head
from app.repositories import (
    IngredientRepository,
    MealRepository,
    WeeklyPlanRepository,
)

#: Point the suite at a real Postgres. Unset means local SQLite files.
TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch) -> Database:
    """A Database isolated to this test, never the app's own data/data.db."""
    shared_url = os.getenv(TEST_DATABASE_URL_ENV_VAR)
    url = shared_url or f"sqlite:///{tmp_path / 'test.db'}"

    monkeypatch.setenv(DATABASE_URL_ENV_VAR, url)

    # The UI caches its Database in st.cache_resource, which would otherwise
    # leak one test's connection - and data - into the next.
    st.cache_resource.clear()

    database = Database(url)
    if shared_url:
        # A server-backed database persists between tests, unlike a temp
        # file, so it has to be emptied explicitly.
        SQLModel.metadata.drop_all(database.engine)

    # Built straight from the models rather than by replaying migrations,
    # which would cost a full DDL run per test. The stamp then tells the
    # application's startup upgrade there is nothing left to apply, and CI
    # separately asserts the migrations and models agree.
    database.create_tables()
    stamp_head(url)
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
