"""Shared dependencies: the database and the repositories over it."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.db import Database, load_env_file
from app.repositories import (
    IngredientRepository,
    MealRepository,
    WeeklyPlanRepository,
)


@dataclass(frozen=True, slots=True)
class Services:
    """Everything a route handler needs to read or change data."""

    db: Database
    meals: MealRepository
    ingredients: IngredientRepository
    plans: WeeklyPlanRepository


@lru_cache(maxsize=1)
def _database() -> Database:
    """One engine per process, so the connection pool is actually reused.

    Establishing a connection costs several network round trips - far more
    than a query - so rebuilding the pool per request would dominate every
    response time.
    """
    load_env_file()
    return Database()


def get_services() -> Services:
    """FastAPI dependency yielding the repositories for one request."""
    db = _database()
    return Services(
        db=db,
        meals=MealRepository(db),
        ingredients=IngredientRepository(db),
        plans=WeeklyPlanRepository(db),
    )


def reset_services_cache() -> None:
    """Drop the cached engine. Used by tests between cases."""
    _database.cache_clear()
