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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

#: Overrides the database location. Set to a Neon/Postgres URL in deployment,
#: to a temporary file by the tests, and left unset for local SQLite.
DATABASE_URL_ENV_VAR = "MEAL_PLANNER_DB_URL"


def load_env_file() -> None:
    """Load .env into the environment, if python-dotenv is available.

    A convenience for local work; deployments provide real environment
    variables or Streamlit secrets, so this quietly does nothing there.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


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
    globals, so tests can point it at a temporary file and a deployment can
    target Postgres without touching a single call site.
    """

    def __init__(self, url: str | None = None, *, echo: bool | None = None) -> None:
        self.url = url or default_database_url()
        if echo is None:
            echo = os.getenv("SQL_ECHO", "false").lower() == "true"

        options: dict[str, object] = {}
        if not self.is_sqlite:
            # A managed Postgres sits behind a network and a pooler, either of
            # which can drop an idle connection. pre-ping checks a connection
            # is alive before handing it out, instead of failing a user's
            # first query after a quiet period.
            options["pool_pre_ping"] = True

        self._engine = create_engine(self.url, echo=echo, **options)

    @property
    def is_sqlite(self) -> bool:
        """True when backed by a local SQLite file rather than a server."""
        return self.url.startswith("sqlite")

    @property
    def engine(self):
        """The underlying SQLAlchemy engine, for Alembic and diagnostics."""
        return self._engine

    def create_tables(self) -> None:
        """Create any missing tables directly from the models.

        Used by the tests, where running the full migration history for each
        of dozens of cases would be needlessly slow. The application itself
        migrates instead, and CI asserts the two agree.
        """
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
