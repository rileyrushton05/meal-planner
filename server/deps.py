"""Shared dependencies: the database and the repositories over it."""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Generator
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


def get_services() -> Generator[Services]:
    """FastAPI dependency yielding the repositories for one request.

    One session is opened here and shared by all three repositories, so a
    request touching several of them costs one BEGIN/COMMIT rather than one
    each. Against a database a network away that was ~1.5s of the 3.4s a
    week change used to take.
    """
    db = _database()
    with db.session() as session:
        yield Services(
            db=db,
            meals=MealRepository(db, session),
            ingredients=IngredientRepository(db, session),
            plans=WeeklyPlanRepository(db, session),
        )


def reset_services_cache() -> None:
    """Drop the cached engine. Used by tests between cases."""
    _database.cache_clear()
