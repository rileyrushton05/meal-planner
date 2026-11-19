"""The accounts migration, run against data shaped like production's.

CI separately applies every migration to an empty database. That proves the
schema, not the data: this upgrades a database holding rows from the
previous revision and checks every row arrives, owned, intact, and that the
upgrade refuses data it cannot carry rather than half-converting it.

Runs on SQLite, and on Postgres when TEST_DATABASE_URL is set (CI's
Postgres leg). Each test starts from an empty schema.
"""

from __future__ import annotations

import os

import pytest
from database_safety import assert_disposable
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.migrations import downgrade_to, upgrade_to

BEFORE = "d8c62df4218c"
ACCOUNTS = "20261117_0001"


@pytest.fixture
def database(tmp_path, db) -> tuple[str, Engine]:
    """An empty database at no revision. Depends on `db` so it runs after
    the shared fixture has built its tables, then clears them away."""
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migrate.db'}"
    engine = create_engine(url)
    if engine.dialect.name == "postgresql":
        assert_disposable(url)
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    yield url, engine
    engine.dispose()


def _run(engine: Engine, *statements: str) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _rows(engine: Engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


def _seed_previous_revision(engine: Engine) -> None:
    """Rows as the pre-accounts app wrote them."""
    _run(
        engine,
        "INSERT INTO meal (id, name, servings, created_at) VALUES "
        "(1, 'Spaghetti Bolognese', 4, '2026-08-20 10:00:00+00:00'), "
        "(2, 'Tacos', 2, '2026-08-21 10:00:00+00:00')",
        "INSERT INTO ingredient (id, name) VALUES "
        "(1, 'Pasta'), (2, 'Beef Mince'), (3, 'Tortillas')",
        # A count-based line written before units were required: unit NULL.
        "INSERT INTO mealingredient (meal_id, ingredient_id, qty, unit) VALUES "
        "(1, 1, 400, 'g'), (1, 2, 500, 'g'), (2, 3, 8, NULL)",
        # Monday planned, Tuesday deliberately cleared, Wednesday planned.
        "INSERT INTO weeklyplan (id, week_start_date, day_of_week, meal_id, servings) "
        "VALUES (1, '2026-08-24', 'Monday', 1, 4), (2, '2026-08-24', 'Tuesday', NULL, NULL), "
        "(3, '2026-08-24', 'Wednesday', 2, 2)",
    )


def test_every_row_arrives_owned_by_one_unclaimed_account(database):
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)

    upgrade_to(url, ACCOUNTS)

    users = _rows(engine, "SELECT id, email, password_hash, is_guest FROM users")
    assert len(users) == 1
    owner, email, password_hash, is_guest = users[0]
    # Unclaimed: no credentials yet, and not a guest, so cleanup never
    # touches it.
    assert (email, password_hash, bool(is_guest)) == (None, None, False)

    assert _rows(
        engine, "SELECT id, user_id, name, servings FROM meals ORDER BY id"
    ) == [
        (1, owner, "Spaghetti Bolognese", 4),
        (2, owner, "Tacos", 2),
    ]
    assert _rows(engine, "SELECT id, user_id, name FROM ingredients ORDER BY id") == [
        (1, owner, "Pasta"),
        (2, owner, "Beef Mince"),
        (3, owner, "Tortillas"),
    ]
    assert _rows(
        engine,
        "SELECT meal_id, ingredient_id, qty, unit FROM meal_ingredients "
        "ORDER BY meal_id, ingredient_id",
    ) == [(1, 1, 400, "g"), (1, 2, 500, "g"), (2, 3, 8, "")]
    assert _rows(
        engine,
        "SELECT id, user_id, day_of_week, meal_id, servings FROM weekly_plans ORDER BY id",
    ) == [
        (1, owner, "Monday", 1, 4),
        (2, owner, "Tuesday", None, None),
        (3, owner, "Wednesday", 2, 2),
    ]


def test_creation_dates_survive(database):
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)

    upgrade_to(url, ACCOUNTS)

    (created,) = _rows(engine, "SELECT created_at FROM meals WHERE id = 1")[0]
    assert str(created).startswith("2026-08-20")


def test_new_rows_continue_after_the_copied_ids(database):
    """Rows keep their ids, so on Postgres each sequence has to restart
    after the highest one; otherwise the next insert collides with row 1."""
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)
    upgrade_to(url, ACCOUNTS)
    (owner,) = _rows(engine, "SELECT id FROM users")[0]

    with engine.begin() as connection:
        new_id = connection.execute(
            text(
                "INSERT INTO meals (user_id, name, servings) "
                f"VALUES ({owner}, 'Pho', 2) RETURNING id"
            )
        ).scalar_one()

    assert new_id == 3


def test_the_old_tables_are_gone(database):
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)

    upgrade_to(url, ACCOUNTS)

    tables = set(inspect(engine).get_table_names())
    assert {"meal", "ingredient", "mealingredient", "weeklyplan"}.isdisjoint(tables)
    assert {
        "users",
        "sessions",
        "meals",
        "ingredients",
        "meal_ingredients",
        "weekly_plans",
    } <= tables


def test_an_empty_database_gets_no_owner_account(database):
    url, engine = database

    upgrade_to(url, ACCOUNTS)

    assert _rows(engine, "SELECT count(*) FROM users") == [(0,)]


def test_rows_pointing_at_deleted_meals_are_resolved_not_fatal(database):
    """SQLite never enforced the old foreign keys, so a local database can
    hold a plan for a deleted meal. It becomes a cleared day, and an
    ingredient line for a deleted meal is dropped."""
    url, engine = database
    if engine.dialect.name != "sqlite":
        pytest.skip(
            "Postgres enforced the old foreign keys, so these rows cannot exist"
        )
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)
    _run(
        engine,
        "INSERT INTO weeklyplan (id, week_start_date, day_of_week, meal_id, servings) "
        "VALUES (4, '2026-08-24', 'Thursday', 99, 3)",
        "INSERT INTO mealingredient (meal_id, ingredient_id, qty, unit) VALUES (99, 1, 5, 'g')",
    )

    upgrade_to(url, ACCOUNTS)

    assert _rows(engine, "SELECT meal_id, servings FROM weekly_plans WHERE id = 4") == [
        (None, None)
    ]
    assert _rows(
        engine, "SELECT count(*) FROM meal_ingredients WHERE meal_id = 99"
    ) == [(0,)]


@pytest.mark.parametrize(
    ("bad_rows", "named_in_error"),
    [
        (
            "INSERT INTO mealingredient (meal_id, ingredient_id, qty, unit) VALUES (2, 1, 0, 'g')",
            "quantity",
        ),
        (
            "INSERT INTO meal (id, name, servings, created_at) VALUES "
            "(3, 'tacos', 2, '2026-08-22 10:00:00+00:00')",
            "tacos",
        ),
        (
            "INSERT INTO weeklyplan (id, week_start_date, day_of_week, meal_id) "
            "VALUES (9, '2026-08-24', 'Funday', 1)",
            "weekday",
        ),
    ],
    ids=["zero quantity", "names differing only in case", "not a weekday"],
)
def test_data_the_new_constraints_would_reject_stops_the_upgrade_untouched(
    database, bad_rows, named_in_error
):
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)
    _run(engine, bad_rows)

    with pytest.raises(RuntimeError, match=named_in_error):
        upgrade_to(url, ACCOUNTS)

    # Nothing changed: still the previous revision, every row in place.
    assert _rows(engine, "SELECT version_num FROM alembic_version") == [(BEFORE,)]
    assert len(_rows(engine, "SELECT id FROM meal")) >= 2


def test_downgrade_restores_the_previous_tables_and_rows(database):
    url, engine = database
    upgrade_to(url, BEFORE)
    _seed_previous_revision(engine)
    before = _rows(
        engine, "SELECT id, day_of_week, meal_id FROM weeklyplan ORDER BY id"
    )
    upgrade_to(url, ACCOUNTS)

    downgrade_to(url, BEFORE)

    assert (
        _rows(engine, "SELECT id, day_of_week, meal_id FROM weeklyplan ORDER BY id")
        == before
    )
    assert _rows(engine, "SELECT name FROM meal ORDER BY id") == [
        ("Spaghetti Bolognese",),
        ("Tacos",),
    ]
    assert "users" not in inspect(engine).get_table_names()


def test_downgrade_refuses_once_two_accounts_own_data(database):
    """The old schema has one plan per day for the whole app, so two
    people's data cannot go back into it without losing some."""
    url, engine = database
    upgrade_to(url, ACCOUNTS)
    _run(
        engine,
        "INSERT INTO users (id, is_guest) VALUES (1, false), (2, true)",
        "INSERT INTO meals (user_id, name, servings) VALUES (1, 'Mine', 1), (2, 'Theirs', 1)",
    )

    with pytest.raises(RuntimeError, match="2 accounts own data"):
        downgrade_to(url, BEFORE)


# --- Every migration, from empty ---------------------------------------------------


def _index_names(engine: Engine) -> set[str]:
    """Read from the catalogue tables directly: SQLAlchemy's reflection skips
    expression indexes on SQLite, which are exactly the ones at risk."""
    sql = (
        "SELECT name FROM sqlite_master WHERE type = 'index'"
        if engine.dialect.name == "sqlite"
        else "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    )
    return {name for (name,) in _rows(engine, sql)}


def test_every_index_the_models_declare_survives_the_migrations(database):
    """SQLite alters a table by rebuilding it, and the rebuild silently
    drops expression indexes, such as the case-insensitive unique names. Two
    migrations lost one that way before this test existed."""
    from sqlmodel import SQLModel

    import app.models  # noqa: F401  (registers every table)

    url, engine = database
    declared = {
        index.name
        for table in SQLModel.metadata.sorted_tables
        for index in table.indexes
    }

    upgrade_to(url, "head")
    assert declared - _index_names(engine) == set()

    # And through the newest migration's downgrade and back.
    downgrade_to(url, "-1")
    upgrade_to(url, "head")
    assert declared - _index_names(engine) == set()
