"""Applying Alembic migrations from Python.

Streamlit Community Cloud has no release phase or deploy hook - it installs
dependencies and starts the app. Running migrations at startup is therefore
the only way to guarantee the schema matches the code that was just
deployed, rather than relying on someone remembering to run them by hand.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    # Set explicitly so the location does not depend on the working directory
    # the app happened to be launched from.
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Alembic stores options in a configparser, where % begins an
    # interpolation token. Percent-encoded characters are common in Postgres
    # passwords, so any literal % has to be doubled.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def upgrade_to_head(url: str) -> None:
    """Bring the database at `url` up to the newest revision.

    A no-op when already current, so it is safe to call on every start.
    Deliberately allowed to raise: a database whose schema does not match
    the code is not something to start up and quietly serve errors from.
    """
    command.upgrade(_alembic_config(url), "head")


def stamp_head(url: str) -> None:
    """Record the database as already at the newest revision, running nothing.

    Used by the tests, which build their schema straight from the models for
    speed. Without the stamp, the application's startup upgrade would try to
    create tables that already exist.
    """
    command.stamp(_alembic_config(url), "head")


def current_revision(url: str) -> str | None:
    """The revision the database is stamped with, or None if unmigrated."""
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
