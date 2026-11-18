"""Leaving, and taking your data with you (server/routers/account.py).

Export must contain only the caller's own data, and nothing secret.
Deletion must remove every row the account owns and nothing anyone else
owns, end every session, and, for an account with a login, need the
password, guessed at no faster than login allows.

The same deletion as the database's restricted runtime role, through row
security, is in tests/test_rls.py.
"""

from __future__ import annotations

import io
import json

import pytest
from api_client import api_client
from sqlalchemy import text

from app.models import ALL_TABLES
from app.ratelimit import LOGIN_PER_ACCOUNT_AND_NETWORK
from server.deps import SESSION_COOKIE
from server.observability import configure_logging

PASSWORD = "lettuce harbour spoon"
EMAIL = "cook@example.com"
PROBLEM = "urn:meal-planner:problem:"
WEEK = "2026-08-03"


def _type(response) -> str:
    return response.json()["type"].removeprefix(PROBLEM)


def _fill(client, meal: str, ingredient: str) -> int:
    """A meal with one ingredient, planned on Monday and Wednesday."""
    created = client.post("/api/meals", json={"name": meal, "servings": 4})
    assert created.status_code == 201, created.text
    meal_id = created.json()["id"]
    added = client.post(
        f"/api/meals/{meal_id}/ingredients",
        json={"name": ingredient, "qty": 400, "unit": "g"},
    )
    assert added.status_code == 200, added.text
    planned = client.put(
        f"/api/plan/{WEEK}",
        json={
            "days": [
                {"day": "Monday", "meal_id": meal_id, "servings": 2},
                {"day": "Tuesday", "meal_id": None},
                {"day": "Wednesday", "meal_id": meal_id},
            ]
        },
    )
    assert planned.status_code == 200, planned.text
    return meal_id


def _user_id(db, email: str | None = None, *, meal: str | None = None) -> int:
    with db.engine.connect() as connection:
        if email is not None:
            query, value = "SELECT id FROM users WHERE email = :v", email
        else:
            query, value = "SELECT user_id FROM meals WHERE name = :v", meal
        return connection.execute(text(query), {"v": value}).scalar_one()


def _rows_owned_by(db, user_id: int) -> dict[str, int]:
    """Every row in every table that belongs to `user_id`: through a user_id
    column, or for meal lines, through their meal. Built from the models,
    so a table added later is checked without anyone remembering to."""
    counts: dict[str, int] = {}
    with db.engine.connect() as connection:
        for model in ALL_TABLES:
            table = model.__table__  # type: ignore[attr-defined]
            if "user_id" in table.c:
                where = "user_id = :id"
            elif table.name == "users":
                where = "id = :id"
            elif table.name == "meal_ingredients":
                where = "meal_id IN (SELECT id FROM meals WHERE user_id = :id)"
            else:
                continue  # rate_limits: keyed hashes, owned by no account
            counts[table.name] = connection.execute(
                text(f"SELECT count(*) FROM {table.name} WHERE {where}"),
                {"id": user_id},
            ).scalar_one()
    return counts


@pytest.fixture
def guest(db):
    with api_client() as client:
        yield client


@pytest.fixture
def account(db):
    """A signed-in account with a meal, an ingredient and a plan."""
    with api_client() as client:
        signed_up = client.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        )
        assert signed_up.status_code == 200, signed_up.text
        _fill(client, "Mine Lasagne", "Pasta")
        yield client


@pytest.fixture
def someone_else(db):
    with api_client() as client:
        _fill(client, "Their Curry", "Rice")
        yield client


@pytest.fixture
def log_lines():
    buffer = io.StringIO()
    configure_logging(stream=buffer, fmt="json")

    def read() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line]

    yield read
    configure_logging()


# --- Export ------------------------------------------------------------------


def test_the_export_is_everything_of_yours_and_nothing_of_anyone_elses(
    account, someone_else
) -> None:
    # An earlier week, planned after the first: every week is included, in
    # calendar order, not the order saved in, nor alphabetical (which an
    # index on the day's name hands back unless told otherwise).
    meal_id = account.get("/api/meals").json()[0]["id"]
    earlier = {
        "days": [
            {"day": "Friday", "meal_id": meal_id},
            {"day": "Wednesday", "meal_id": meal_id},
        ]
    }
    assert account.put("/api/plan/2026-07-27", json=earlier).status_code == 200

    response = account.get("/api/account/export")

    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "meal-planner-export"
    assert body["account"]["email"] == EMAIL
    assert body["account"]["is_guest"] is False
    assert [m["name"] for m in body["meals"]] == ["Mine Lasagne"]
    assert body["meals"][0]["ingredients"] == [
        {"name": "Pasta", "qty": 400, "unit": "g"}
    ]
    # Planned days by meal name, in calendar order; a cleared day is not data.
    assert body["plans"] == [
        {
            "week_start": "2026-07-27",
            "day": "Wednesday",
            "meal": "Mine Lasagne",
            "servings": None,
        },
        {
            "week_start": "2026-07-27",
            "day": "Friday",
            "meal": "Mine Lasagne",
            "servings": None,
        },
        {"week_start": WEEK, "day": "Monday", "meal": "Mine Lasagne", "servings": 2},
        {
            "week_start": WEEK,
            "day": "Wednesday",
            "meal": "Mine Lasagne",
            "servings": None,
        },
    ]
    assert "Their Curry" not in response.text
    assert "Rice" not in response.text


def test_the_export_holds_no_secrets_and_no_internal_ids(account, db) -> None:
    response = account.get("/api/account/export")

    with db.engine.connect() as connection:
        password_hash = connection.execute(
            text("SELECT password_hash FROM users WHERE email = :e"), {"e": EMAIL}
        ).scalar_one()
    assert password_hash not in response.text
    assert account.cookies.get(SESSION_COOKIE) not in response.text
    assert '"id"' not in response.text and '"user_id"' not in response.text


def test_the_export_downloads_as_a_file(guest) -> None:
    response = guest.get("/api/account/export")

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="meal-planner-export-')
    assert disposition.endswith('.json"')
    assert response.json()["account"] == {
        "email": None,
        "is_guest": True,
        "created_at": response.json()["account"]["created_at"],
    }


# --- Deletion: a guest -------------------------------------------------------


def test_a_guest_deletes_everything_without_a_password(guest, someone_else, db) -> None:
    _fill(guest, "Guest Soup", "Leek")
    me = _user_id(db, meal="Guest Soup")
    them = _user_id(db, meal="Their Curry")
    theirs_before = _rows_owned_by(db, them)

    response = guest.delete("/api/account")

    assert response.status_code == 204
    assert set(_rows_owned_by(db, me).values()) == {0}
    assert _rows_owned_by(db, them) == theirs_before
    # Signed out: the cookie is cleared, and the old token is dead too.
    assert guest.cookies.get(SESSION_COOKIE) is None
    assert guest.get("/api/auth/me").status_code == 401


# --- Deletion: an account ----------------------------------------------------


@pytest.mark.parametrize(
    "body", [None, {}, {"password": "not the password"}], ids=["none", "empty", "wrong"]
)
def test_an_account_needs_its_password(account, db, body) -> None:
    me = _user_id(db, EMAIL)
    before = _rows_owned_by(db, me)

    response = account.request("DELETE", "/api/account", json=body)

    assert response.status_code == 401
    assert _type(response) == "invalid-credentials"
    assert response.json()["detail"] == "That password isn't right."
    assert _rows_owned_by(db, me) == before
    # Still signed in: a mistyped password is not a sign-out.
    assert account.get("/api/auth/me").status_code == 200


def test_with_its_password_an_account_and_everything_in_it_goes(
    account, someone_else, db
) -> None:
    me = _user_id(db, EMAIL)
    them = _user_id(db, meal="Their Curry")
    theirs_before = _rows_owned_by(db, them)
    # A second browser signed in to the same account.
    with api_client(as_guest=False) as other_browser:
        other_browser.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert other_browser.get("/api/auth/me").status_code == 200

        response = account.request(
            "DELETE", "/api/account", json={"password": PASSWORD}
        )

        assert response.status_code == 204
        assert set(_rows_owned_by(db, me).values()) == {0}
        assert _rows_owned_by(db, them) == theirs_before
        # Every session ended, not only this one.
        assert other_browser.get("/api/auth/me").status_code == 401
    # The credentials are gone: they sign in to nothing.
    with api_client(as_guest=False) as later:
        login = later.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert login.status_code == 401
        # And the email is free to sign up with again.
        signup = later.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        )
        assert signup.status_code == 200


def test_guessing_the_password_is_throttled_with_login(account) -> None:
    """Otherwise a stolen session could guess the password here, unthrottled,
    and then use it wherever else it was reused."""
    for _ in range(LOGIN_PER_ACCOUNT_AND_NETWORK.free):
        wrong = account.request("DELETE", "/api/account", json={"password": "guess"})
        assert wrong.status_code == 401

    refused = account.request("DELETE", "/api/account", json={"password": PASSWORD})
    assert refused.status_code == 429
    # The same throttle as login: signing in is refused for now too.
    with api_client(as_guest=False) as browser:
        login = browser.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert login.status_code == 429


def test_deletion_is_logged_without_saying_who(account, db, log_lines) -> None:
    me = _user_id(db, EMAIL)

    account.request("DELETE", "/api/account", json={"password": PASSWORD})

    [event] = [line for line in log_lines() if line.get("event") == "account_deleted"]
    assert event["user_id"] == me
    assert event["removed"] == {"meals": 1, "ingredients": 1, "plans": 3, "sessions": 1}
    logged = json.dumps(log_lines())
    assert EMAIL not in logged and PASSWORD not in logged


def test_a_wrong_password_here_is_logged_as_not_a_login(account, log_lines) -> None:
    account.request("DELETE", "/api/account", json={"password": "guess"})

    [event] = [line for line in log_lines() if line.get("event") == "login_failed"]
    assert event["outcome"] == "delete_account"
