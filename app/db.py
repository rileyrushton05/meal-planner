"""Database engine ownership and transactional session handling."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

# Imported for the side effect of registering the table models with
# SQLModel.metadata, so create_tables() below knows about them. Never
# referenced directly.
from app import models  # noqa: F401

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


#: Overrides the database location. Lets tests point at a temporary file and
#: would let a deployment target a managed database without a code change.
DATABASE_URL_ENV_VAR = "MEAL_PLANNER_DB_URL"


def default_database_url() -> str:
    """Where the app stores its data, unless overridden by the environment.

    The on-disk fallback is resolved from this file's location rather than
    the working directory, so the path is identical however the app is
    launched (terminal, IDE run button, Streamlit Cloud).
    """
    configured = os.getenv(DATABASE_URL_ENV_VAR)
    if configured:
        return configured

    DEFAULT_DATA_DIR.mkdir(exist_ok=True)
    return f"sqlite:///{DEFAULT_DATA_DIR / 'data.db'}"


class Database:
    """Owns a SQLAlchemy engine and hands out transactional sessions.

    Constructed with an explicit URL rather than reading module-level
    globals, so tests can point it at a temporary file and the app can
    later target a different backend without touching call sites.
    """

    def __init__(self, url: str | None = None, *, echo: bool | None = None) -> None:
        if url is None:
            url = default_database_url()
        if echo is None:
            echo = os.getenv("SQL_ECHO", "false").lower() == "true"
        self._engine = create_engine(url, echo=echo)

    def create_tables(self) -> None:
        """Create any tables that don't exist yet. Never alters existing ones."""
        SQLModel.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session]:
        """Yield a session that commits on success and rolls back on error.

        Every repository method runs inside one of these, which is what
        makes multi-step writes (a meal plus all its ingredients) atomic.
        """
        # expire_on_commit=False keeps attributes readable after the
        # session closes, so repository methods can return ORM objects
        # to callers that have no session of their own.
        session = Session(self._engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
