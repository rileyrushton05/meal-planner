"""Alembic environment.

Targets whatever database the application targets: the URL comes from
MEAL_PLANNER_DB_URL, falling back to the local SQLite file, so `alembic`
run by hand and the migration run at app startup can never disagree.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from app.db import default_database_url, load_env_file

# Importing the models registers every table on SQLModel.metadata, which is
# what autogenerate diffs the live database against.
from app import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_env_file()

# configparser treats % as interpolation syntax, and Postgres passwords are
# percent-encoded, so any literal % has to be escaped before being stored.
config.set_main_option("sqlalchemy.url", default_database_url().replace("%", "%%"))

target_metadata = SQLModel.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or manual apply."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # SQLite cannot ALTER most things in place; batch mode rebuilds the
        # table instead. Harmless to leave on only where it is needed.
        render_as_batch=_is_sqlite(url or ""),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
