"""Who opens, commits and rolls back transactions, and what that guarantees.

The rule (docs/conventions.md, C6): `Database.transaction()` is the only
place anything commits. The API opens one per request; repositories work
inside whatever they are handed and never decide the outcome themselves.
"""

from __future__ import annotations

import threading
import time

import pytest
from api_client import api_client
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session as OrmSession

import app.exceptions as app_exceptions
from app.db import Database
from app.exceptions import KeepsWrites, MealPlannerError
from app.repositories import IngredientRepository, MealRepository


class _Abandon(Exception):
    """Raised inside a transaction to make it roll back."""


@pytest.fixture
def client(db):
    with api_client(raise_server_exceptions=False) as test_client:
        yield test_client


# --- Repositories never decide the outcome ------------------------------------


def test_work_done_through_a_repository_is_kept_only_if_the_caller_commits(
    db: Database, user_id: int
) -> None:
    with pytest.raises(_Abandon), db.transaction() as session:
        MealRepository(session, user_id=user_id).add("Spaghetti")
        raise _Abandon

    with db.transaction() as session:
        assert MealRepository(session, user_id=user_id).list_all() == []


class _RecordedThenFailed(KeepsWrites, MealPlannerError):
    """Like a failed login: an error whose request keeps what it recorded."""


def test_an_error_marked_keeps_writes_commits_what_came_before_it(
    db: Database, user_id: int
) -> None:
    with pytest.raises(_RecordedThenFailed), db.transaction() as session:
        MealRepository(session, user_id=user_id).add("Recorded")
        raise _RecordedThenFailed("refused, but counted")

    with db.transaction() as session:
        names = [m.name for m in MealRepository(session, user_id=user_id).list_all()]
    assert names == ["Recorded"]


def test_only_marked_errors_keep_writes() -> None:
    marked = {
        cls
        for cls in vars(app_exceptions).values()
        if isinstance(cls, type)
        and issubclass(cls, KeepsWrites)
        and cls is not KeepsWrites
    }
    # Each of these must be raised before anything but its record is
    # written; adding one is a decision, so it is listed here.
    assert marked == {
        app_exceptions.InvalidCredentialsError,
        app_exceptions.EmailTakenError,
        # Raised after counting the attempt and fetching, before any write
        # of the caller's data (an import saves nothing).
        app_exceptions.RecipeImportError,
    }


def test_a_whole_request_lands_together(db: Database, user_id: int) -> None:
    with db.transaction() as session:
        meals = MealRepository(session, user_id=user_id)
        meal = meals.add("Omelette")
        meals.add_ingredient(meal.id or 0, "Eggs", 3, "")

    with db.transaction() as session:
        [(saved, lines)] = MealRepository(
            session, user_id=user_id
        ).list_all_with_ingredients()
        assert saved.name == "Omelette"
        assert [ingredient.name for _, ingredient in lines] == ["Eggs"]


def test_nothing_can_run_outside_a_transaction(db: Database, user_id: int) -> None:
    # A repository kept past its transaction (a stray read after commit, a
    # lazy load in a response) must fail, not quietly start a transaction
    # that nothing will commit or close.
    with db.transaction() as session:
        meals = MealRepository(session, user_id=user_id)

    with pytest.raises(InvalidRequestError, match=r"[Aa]utobegin"):
        meals.list_all()


# --- Through the API ------------------------------------------------------------


def test_a_request_that_fails_part_way_writes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The template route creates the meal, then adds its ingredients one by
    # one. Fail on the second ingredient: the meal and the first ingredient
    # were already written in this request's transaction.
    real = MealRepository._get_or_create_ingredient
    calls = 0

    def fail_on_second(self, name):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("the database went away")
        return real(self, name)

    monkeypatch.setattr(MealRepository, "_get_or_create_ingredient", fail_on_second)

    response = client.post("/api/meals/from-template/Spaghetti Bolognese")
    assert response.status_code == 500
    assert calls == 2

    monkeypatch.undo()
    assert client.get("/api/meals").json() == []


def test_a_commit_that_fails_is_never_reported_as_success(client: TestClient) -> None:
    # With FastAPI's default dependency scope, the commit runs after the
    # response has been sent: this request answered 201, and the meal did
    # not exist. scope="function" in server/deps.py is what makes it a 500.
    def fail_commit(session) -> None:
        raise RuntimeError("connection lost during COMMIT")

    event.listen(OrmSession, "before_commit", fail_commit)
    try:
        response = client.post("/api/meals", json={"name": "Spaghetti", "servings": 4})
    finally:
        event.remove(OrmSession, "before_commit", fail_commit)

    assert response.status_code == 500, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert client.get("/api/meals").json() == []


# --- Creating the same ingredient twice at once ---------------------------------


def test_an_ingredient_created_by_someone_else_mid_request_is_reused(
    db: Database, user_id: int, meals, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race, replayed deterministically on either database.

    Another request has already created "Eggs", but this one looked before
    that committed and saw nothing. Its insert must then find the row and
    use it. A plain INSERT would raise on the unique index here, and in
    Postgres would abort the rest of the request with it.
    """
    omelette = meals.add("Omelette")
    frittata = meals.add("Frittata")
    meals.add_ingredient(omelette.id, "Eggs", 2, "")

    real_find = MealRepository._find_ingredient_by_name
    lookups = 0

    def miss_the_first_lookup(self, name):
        nonlocal lookups
        lookups += 1
        return None if lookups == 1 else real_find(self, name)

    monkeypatch.setattr(
        MealRepository, "_find_ingredient_by_name", miss_the_first_lookup
    )
    meals.add_ingredient(frittata.id, "eggs", 3, "")
    monkeypatch.undo()

    assert lookups == 2, "should have looked, inserted, and looked again"
    with db.transaction() as session:
        assert [
            i.name for i in IngredientRepository(session, user_id=user_id).list_all()
        ] == ["Eggs"]
    [(_, eggs_in_omelette)] = meals.list_ingredients(omelette.id)
    [(_, eggs_in_frittata)] = meals.list_ingredients(frittata.id)
    assert eggs_in_omelette.id == eggs_in_frittata.id


def _wait_until_a_query_is_blocked_on_a_lock(db: Database, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    with db.engine.connect() as connection:
        while time.monotonic() < deadline:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            ).scalar()
            connection.rollback()
            if waiting:
                return
            time.sleep(0.02)
    raise AssertionError("the second request never waited on the first")


def test_two_requests_creating_the_same_new_ingredient_at_once_both_succeed(
    db: Database, user_id: int, meals
) -> None:
    """The real race, with two concurrent transactions in Postgres.

    The first request inserts "Eggs" and holds its transaction open. The
    second, adding "eggs", cannot see that uncommitted row, so its insert
    waits on the unique index. When the first commits, the second's
    ON CONFLICT DO NOTHING applies and it reuses the committed row.
    """
    if db.is_sqlite:
        pytest.skip("SQLite runs one writer at a time, so this race cannot happen")

    omelette = meals.add("Omelette").id
    frittata = meals.add("Frittata").id
    first_has_inserted = threading.Event()
    let_first_commit = threading.Event()
    errors: list[BaseException] = []

    def first_request() -> None:
        try:
            with db.transaction() as session:
                MealRepository(session, user_id=user_id).add_ingredient(
                    omelette, "Eggs", 2, ""
                )
                first_has_inserted.set()
                let_first_commit.wait(10)
        except BaseException as error:
            errors.append(error)
            first_has_inserted.set()

    def second_request() -> None:
        try:
            with db.transaction() as session:
                MealRepository(session, user_id=user_id).add_ingredient(
                    frittata, "eggs", 3, ""
                )
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=first_request)
    second = threading.Thread(target=second_request)
    first.start()
    assert first_has_inserted.wait(10)
    second.start()
    try:
        _wait_until_a_query_is_blocked_on_a_lock(db)
    finally:
        let_first_commit.set()
        first.join(10)
        second.join(10)

    assert errors == []
    with db.transaction() as session:
        assert [
            i.name for i in IngredientRepository(session, user_id=user_id).list_all()
        ] == ["Eggs"]
    [(_, in_omelette)] = meals.list_ingredients(omelette)
    [(_, in_frittata)] = meals.list_ingredients(frittata)
    assert in_omelette.id == in_frittata.id
