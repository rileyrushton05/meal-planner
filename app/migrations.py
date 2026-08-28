"""Applying Alembic migrations from Python, for use at application startup."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    # Explicit so the location does not depend on the working directory.
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Alembic stores options in a configparser, where % starts an
    # interpolation token; Postgres passwords are often percent-encoded.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def upgrade_to_head(url: str) -> None:
    """Bring the database up to the newest revision.

    A no-op when already current, and allowed to raise: a schema that does
    not match the code should stop startup, not serve errors quietly.
    """
    command.upgrade(_alembic_config(url), "head")


def stamp_head(url: str) -> None:
    """Mark the database as current without running anything.

    For tests, which build their schema from the models; without it the
    startup upgrade would try to create tables that already exist.
    """
    command.stamp(_alembic_config(url), "head")
