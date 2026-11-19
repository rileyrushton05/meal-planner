"""Row-level security, proved at the database, as the role the app runs as.

The repositories scope every query to one user. These tests bypass them and
query the tables directly, connected as `meal_planner_app` to a schema built
by the real migrations (not `create_all`, which knows nothing of policies),
to show Postgres enforces the same thing on its own: a query that forgot its
`WHERE user_id = ...` still sees, and can change, only one person's rows.

Postgres only. Skipped on the SQLite leg, which has no row security.
"""

from __future__ import annotations

import os

import pytest
from api_client import api_client
from database_safety import assert_disposable
from sqlalchemy import Engine, column, create_engine, func, inspect, table, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlmodel import Session, select

from app.db import RUNTIME_ROLE, act_as, is_local_database
from app.migrations import upgrade_to_head
from app.models import ALL_TABLES, Ingredient, Meal, MealIngredient, WeeklyPlan
from app.readiness import check_database_ready

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="row-level security is a Postgres feature",
)

#: Tables the runtime role uses without row security, because their rows
#: belong to no one user: signing in has to find a session or an email
#: before anyone is known, and throttle buckets are keyed by hashed
#: networks and emails, not accounts.
AUTH_TABLES = {"users", "sessions", "rate_limits"}
#: A password for the test server only, never a real deployment's.
TEST_PASSWORD = "rls-test-only-password"
ALICE, BOB = 1, 2


@pytest.fixture
def owner(db) -> Engine:
    """The test database rebuilt by the migrations, holding two users' rows.

    Depends on `db` so it runs after the shared fixture, then replaces that
    schema. The role password is set on the test server only, and only on
    one that is disposable and on this machine.
    """
    url = os.environ["TEST_DATABASE_URL"]
    assert_disposable(url)
    assert is_local_database(url), "sets a role password; local servers only"

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    upgrade_to_head(url)
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER ROLE {RUNTIME_ROLE} WITH LOGIN PASSWORD '{TEST_PASSWORD}'")
        )
        for statement in (
            "INSERT INTO users (id, is_guest) VALUES (1, true), (2, true)",
            "INSERT INTO meals (id, user_id, name, servings) VALUES "
            "(1, 1, 'Alice Pasta', 2), (2, 2, 'Bob Curry', 4)",
            "INSERT INTO ingredients (id, user_id, name) VALUES "
            "(1, 1, 'Pasta'), (2, 2, 'Rice')",
            "INSERT INTO meal_ingredients (meal_id, ingredient_id, qty, unit) "
            "VALUES (1, 1, 200, 'g'), (2, 2, 300, 'g')",
            "INSERT INTO weekly_plans (id, user_id, week_start_date, day_of_week, "
            "meal_id) VALUES (1, 1, '2026-08-03', 'Monday', 1), "
            "(2, 2, '2026-08-03', 'Monday', 2)",
        ):
            connection.execute(text(statement))
        for table in ("users", "meals", "ingredients", "weekly_plans"):
            connection.execute(
                text(f"SELECT setval('{table}_id_seq', (SELECT max(id) FROM {table}))")
            )
    yield engine
    engine.dispose()


@pytest.fixture
def runtime_url(owner: Engine) -> str:
    url = make_url(os.environ["TEST_DATABASE_URL"])
    return url.set(username=RUNTIME_ROLE, password=TEST_PASSWORD).render_as_string(
        hide_password=False
    )


@pytest.fixture
def app_role(runtime_url: str) -> Engine:
    engine = create_engine(runtime_url)
    yield engine
    engine.dispose()


def _as(app_role: Engine, user_id: int | None) -> Session:
    """A transaction as the runtime role, acting for `user_id` (or no one)."""
    session = Session(app_role, autobegin=False)
    session.begin()
    if user_id is not None:
        act_as(session, user_id)
    return session


# --- The role itself ---------------------------------------------------------------


def test_the_runtime_role_cannot_bypass_row_security(app_role: Engine) -> None:
    with app_role.connect() as connection:
        row = connection.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
    assert tuple(row) == (RUNTIME_ROLE, False, False)


def test_every_table_is_under_row_security_unless_it_is_an_auth_table(
    owner: Engine,
) -> None:
    with owner.connect() as connection:
        protected = dict(
            connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity AND EXISTS ("
                    "  SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                    "AND c.relname <> 'alembic_version'"
                )
            ).all()
        )
    # A new table holding someone's data must get a policy, or be named here
    # with a reason.
    assert set(protected) == {model.__table__.name for model in ALL_TABLES}  # type: ignore[attr-defined]
    assert {t for t, on in protected.items() if not on} == AUTH_TABLES


def test_the_runtime_role_cannot_change_the_schema(app_role: Engine) -> None:
    with app_role.connect() as connection, pytest.raises(ProgrammingError):
        connection.execute(text("CREATE TABLE sneaky (id int)"))


def test_the_runtime_role_cannot_rewrite_migration_history(app_role: Engine) -> None:
    with app_role.connect() as connection, pytest.raises(ProgrammingError):
        connection.execute(text("SELECT * FROM alembic_version"))


# --- Reading -----------------------------------------------------------------------


def test_an_unscoped_query_sees_only_the_declared_users_rows(app_role: Engine) -> None:
    # No WHERE user_id at all, as if a repository forgot it.
    with _as(app_role, ALICE) as session:
        assert [m.name for m in session.exec(select(Meal))] == ["Alice Pasta"]
        assert [i.name for i in session.exec(select(Ingredient))] == ["Pasta"]
        assert [p.meal_id for p in session.exec(select(WeeklyPlan))] == [1]
        assert [(line.meal_id) for line in session.exec(select(MealIngredient))] == [1]


def test_asking_for_someone_elses_meal_by_id_finds_nothing(app_role: Engine) -> None:
    with _as(app_role, ALICE) as session:
        assert session.get(Meal, 2) is None


def test_a_request_that_never_declares_a_user_sees_nothing(app_role: Engine) -> None:
    with _as(app_role, None) as session:
        for model in (Meal, Ingredient, MealIngredient, WeeklyPlan):
            assert session.exec(select(model)).all() == []


def test_the_declared_user_ends_with_the_transaction(app_role: Engine) -> None:
    # Pooled connections are reused across requests; the identity must not be.
    with app_role.connect() as connection:
        with connection.begin():
            connection.execute(text("SELECT set_config('app.user_id', '1', true)"))
            assert connection.execute(text("SELECT count(*) FROM meals")).scalar() == 1
        with connection.begin():
            assert connection.execute(text("SELECT count(*) FROM meals")).scalar() == 0


# --- Writing -----------------------------------------------------------------------


def test_someone_elses_rows_cannot_be_changed_or_deleted(app_role: Engine) -> None:
    with _as(app_role, ALICE) as session:
        renamed = session.execute(text("UPDATE meals SET name = 'Mine' WHERE id = 2"))
        deleted = session.execute(text("DELETE FROM meals WHERE id = 2"))
        cleared = session.execute(text("DELETE FROM weekly_plans"))
        session.commit()
    assert (renamed.rowcount, deleted.rowcount, cleared.rowcount) == (0, 0, 1)


@pytest.mark.parametrize(
    "statement",
    [
        # A row owned by someone else.
        "INSERT INTO meals (user_id, name, servings) VALUES (2, 'Planted', 1)",
        "UPDATE meals SET user_id = 2 WHERE id = 1",
        # A plan naming someone else's meal.
        "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week, meal_id) "
        "VALUES (1, '2026-08-10', 'Monday', 2)",
        # A line putting someone else's ingredient on my meal.
        "INSERT INTO meal_ingredients (meal_id, ingredient_id, qty, unit) "
        "VALUES (1, 2, 1, '')",
    ],
)
def test_rows_that_would_belong_to_or_point_at_someone_else_are_refused(
    app_role: Engine, statement: str
) -> None:
    with _as(app_role, ALICE) as session, pytest.raises(DBAPIError) as refused:
        session.execute(text(statement))
    assert "row-level security" in str(refused.value)


# --- The whole app, running as the role ------------------------------------------


@pytest.fixture
def runtime_client(runtime_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEAL_PLANNER_DB_URL", runtime_url)
    monkeypatch.setenv("MEAL_PLANNER_AUTO_MIGRATE", "false")
    with api_client(as_guest=False) as client:
        yield client


def test_readiness_works_as_the_runtime_role_without_migration_table_access(
    owner: Engine, runtime_client
) -> None:

    def sequence_values():
        with owner.connect() as connection:
            values = {}
            for name in inspect(connection).get_sequence_names():
                sequence = table(name, column("last_value"), column("is_called"))
                values[name] = tuple(connection.execute(select(sequence)).one())
            return values

    before = sequence_values()
    assert runtime_client.get("/health/ready").json() == {"status": "ok"}
    assert sequence_values() == before


@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
def test_readiness_restores_connection_timeouts(owner: Engine, fail: bool) -> None:
    # A single pooled connection proves settings do not leak to its next user.
    engine = create_engine(owner.url, pool_size=1, max_overflow=0)
    statement = select(
        func.current_setting("statement_timeout"),
        func.current_setting("lock_timeout"),
    )
    try:
        with engine.connect() as connection:
            before = connection.execute(statement).one()
        if fail:
            with owner.begin() as connection:
                connection.execute(
                    text("ALTER TABLE users RENAME COLUMN email TO old_email")
                )
            with pytest.raises(ProgrammingError):
                check_database_ready(engine)
        else:
            check_database_ready(engine)
        with engine.connect() as connection:
            assert connection.execute(statement).one() == before
    finally:
        engine.dispose()


def test_readiness_checks_the_rls_helper_when_another_table_uses_rls(
    owner: Engine, runtime_client
) -> None:
    with owner.begin() as connection:
        connection.execute(text("ALTER TABLE meals DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                "REVOKE EXECUTE ON FUNCTION current_app_user_id() "
                f"FROM PUBLIC, {RUNTIME_ROLE}"
            )
        )
    # Ingredients and plans still use the helper even with meals' policy off.
    assert runtime_client.get("/health/ready").status_code == 503


@pytest.mark.parametrize(
    "revocation",
    [
        f"REVOKE SELECT ON users FROM {RUNTIME_ROLE}",
        f"REVOKE INSERT ON meals FROM {RUNTIME_ROLE}",
        f"REVOKE UPDATE ON sessions FROM {RUNTIME_ROLE}",
        f"REVOKE DELETE ON weekly_plans FROM {RUNTIME_ROLE}",
        f"REVOKE USAGE ON SEQUENCE users_id_seq FROM {RUNTIME_ROLE}",
        f"REVOKE EXECUTE ON FUNCTION current_app_user_id() FROM PUBLIC, {RUNTIME_ROLE}",
    ],
)
def test_readiness_refuses_missing_runtime_permissions(
    owner: Engine,
    runtime_client,
    revocation: str,
) -> None:
    with owner.begin() as connection:
        connection.execute(text(revocation))
    response = runtime_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["type"] == "urn:meal-planner:problem:not-ready"
    assert "permission" not in response.text
    assert runtime_client.get("/health/live").status_code == 200


def test_the_app_works_end_to_end_as_the_runtime_role(
    runtime_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As deployed: the runtime role, under RLS, never migrating at startup
    # (it has no access to alembic_version).
    monkeypatch.setenv("MEAL_PLANNER_DB_URL", runtime_url)
    monkeypatch.setenv("MEAL_PLANNER_AUTO_MIGRATE", "false")

    with api_client() as client:
        assert client.get("/api/meals").json() == []  # not Alice's, not Bob's

        meal = client.post("/api/meals/from-template/Spaghetti Bolognese").json()
        assert len(meal["ingredients"]) >= 3
        plan = {"days": [{"day": "Monday", "meal_id": meal["id"]}]}
        assert client.put("/api/plan/2026-08-03", json=plan).status_code == 200
        groceries = client.get("/api/grocery-list/2026-08-03").json()
        assert {line["name"] for line in groceries} == {
            i["name"] for i in meal["ingredients"]
        }
        assert client.post("/api/plan/2026-08-10/copy-previous").status_code == 200

        # Bob's meal 2 exists, and is invisible.
        assert client.get("/api/meals/2").status_code == 404
        bad_plan = {"days": [{"day": "Tuesday", "meal_id": 2}]}
        assert client.put("/api/plan/2026-08-03", json=bad_plan).status_code == 404

        signup = {"email": "rls@example.com", "password": "lettuce harbour spoon"}
        assert client.post("/api/auth/signup", json=signup).status_code == 200
        assert client.delete(f"/api/meals/{meal['id']}").status_code == 204
        assert client.post("/api/auth/logout").status_code == 204


def test_a_guests_sample_meals_are_written_under_row_security(
    runtime_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Guest creation declares the new user before writing their samples;
    # without that, the policies would refuse every sample row.
    monkeypatch.setenv("MEAL_PLANNER_DB_URL", runtime_url)
    monkeypatch.setenv("MEAL_PLANNER_AUTO_MIGRATE", "false")

    with api_client(as_guest=False) as client:
        started = client.post("/api/auth/guest", json={"sample_week": "2026-08-05"})
        assert started.status_code == 201, started.text
        assert len(client.get("/api/meals").json()) == 3


def test_deleting_an_account_as_the_runtime_role_takes_everything_and_only_it(
    owner: Engine, runtime_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cascade from `users` runs through tables under row security. It
    must reach all of the account's rows (with counts read under the
    policies), and none of Alice's or Bob's."""
    monkeypatch.setenv("MEAL_PLANNER_DB_URL", runtime_url)
    monkeypatch.setenv("MEAL_PLANNER_AUTO_MIGRATE", "false")

    with api_client() as client:
        meal = client.post("/api/meals/from-template/Spaghetti Bolognese").json()
        plan = {"days": [{"day": "Monday", "meal_id": meal["id"]}]}
        assert client.put("/api/plan/2026-08-03", json=plan).status_code == 200
        signup = {"email": "leaving@example.com", "password": "lettuce harbour spoon"}
        assert client.post("/api/auth/signup", json=signup).status_code == 200
        with owner.connect() as connection:
            me = connection.execute(
                text("SELECT id FROM users WHERE email = 'leaving@example.com'")
            ).scalar_one()

        deleted = client.request(
            "DELETE", "/api/account", json={"password": "lettuce harbour spoon"}
        )
        assert deleted.status_code == 204, deleted.text

    with owner.connect() as connection:
        mine = {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id = :id"), {"id": me}
            ).scalar_one()
            for table in ("meals", "ingredients", "weekly_plans", "sessions")
        }
        lines = connection.execute(
            text("SELECT count(*) FROM meal_ingredients WHERE meal_id = :m"),
            {"m": meal["id"]},
        ).scalar_one()
        others = connection.execute(
            text("SELECT count(*) FROM meals WHERE user_id IN (1, 2)")
        ).scalar_one()
    assert mine == {"meals": 0, "ingredients": 0, "weekly_plans": 0, "sessions": 0}
    assert lines == 0
    assert others == 2
