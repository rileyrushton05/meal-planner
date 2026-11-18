"""Signing in, staying signed in, and signing out, through the HTTP API.

Each section maps to a row of the accounts plan's "what gets tested" table.
Throttling and security logging arrive with Phase 1, step 6.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest
from api_client import api_client
from argon2 import PasswordHasher, extract_parameters, profiles
from sqlalchemy import text

from app.auth import REFRESH_INTERVAL, SESSION_LIFETIME, AuthService
from app.db import Database
from app.exceptions import NotSignedInError
from app.repositories import UserRepository
from app.security import PASSWORD_PARAMETERS
from server.deps import SESSION_COOKIE
from server.main import app

PASSWORD = "lettuce harbour spoon"
EMAIL = "cook@example.com"
PROBLEM = "urn:meal-planner:problem:"


@pytest.fixture
def guest(db):
    with api_client() as client:
        yield client


@pytest.fixture
def anonymous(db):
    with api_client(as_guest=False) as client:
        yield client


def _token(client) -> str:
    token = client.cookies.get(SESSION_COOKIE)
    assert token, "no session cookie"
    return token


def _as(client, token: str) -> dict[str, str]:
    """Headers presenting a specific session token, from a client with none."""
    assert client.cookies.get(SESSION_COOKIE) is None
    return {"cookie": f"{SESSION_COOKIE}={token}"}


def _sign_up(client, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def _log_in(client, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _problem_type(response) -> str:
    return response.json()["type"].removeprefix(PROBLEM)


# --- Every data route needs a session ------------------------------------------


def _every_data_route() -> list[tuple[str, str]]:
    """From the OpenAPI document, which lists every route the app serves."""
    examples = {
        "meal_id": "1",
        "ingredient_id": "1",
        "week": "2026-08-03",
        "template_name": "Omelette",
    }
    routes = []
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/") or path.startswith("/api/auth/"):
            continue
        concrete = re.sub(r"\{(\w+)\}", lambda m: examples[m.group(1)], path)
        routes.extend((method.upper(), concrete) for method in sorted(operations))
    return routes


DATA_ROUTES = _every_data_route()


def test_the_route_list_is_not_empty() -> None:
    assert ("GET", "/api/state") in DATA_ROUTES
    assert ("POST", "/api/meals") in DATA_ROUTES
    assert len(DATA_ROUTES) >= 14


@pytest.mark.parametrize(("method", "path"), DATA_ROUTES)
def test_every_data_route_answers_401_without_a_session(anonymous, method, path):
    # Built from the app's own route table, so a route added later without
    # the session dependency fails here rather than shipping open.
    response = anonymous.request(method, path, json={})
    assert response.status_code == 401, response.text
    assert _problem_type(response) == "not-signed-in"


def test_a_made_up_token_is_not_signed_in(anonymous):
    response = anonymous.get("/api/state", headers=_as(anonymous, "x" * 43))
    assert response.status_code == 401


# --- Guests ----------------------------------------------------------------------


def test_a_guest_session_is_a_real_account_with_no_credentials(anonymous):
    response = anonymous.post("/api/auth/guest")

    assert response.status_code == 201
    guest = {"email": None, "is_guest": True, "has_recovery_code": False}
    assert response.json() == guest
    assert anonymous.get("/api/auth/me").json() == guest
    assert anonymous.get("/api/meals").json() == []


def test_the_session_cookie_cannot_be_read_by_scripts_or_sent_cross_site(anonymous):
    cookie = anonymous.post("/api/auth/guest").headers["set-cookie"]
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")}

    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert {"httponly", "secure", "path", "samesite", "max-age"} <= attributes
    assert re.search(r"samesite=strict", cookie, re.IGNORECASE)
    assert "path=/" in cookie.lower()
    assert "domain" not in attributes, "__Host- cookies must not set Domain"


def test_asking_for_a_guest_session_twice_keeps_the_first(guest):
    before = _token(guest)
    response = guest.post("/api/auth/guest")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert _token(guest) == before


def test_only_a_hash_of_the_token_is_stored(guest, db: Database):
    token = _token(guest)
    with db.engine.connect() as connection:
        stored = connection.execute(text("SELECT token_hash FROM sessions")).scalars()
        stored = list(stored)

    assert stored == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in stored


def test_two_guests_cannot_see_or_touch_each_others_meals(guest, db):
    meal = guest.post("/api/meals", json={"name": "Spaghetti", "servings": 4}).json()

    with api_client() as stranger:
        assert stranger.get("/api/meals").json() == []
        # 404, not 403: a 403 would confirm the id belongs to someone.
        assert stranger.get(f"/api/meals/{meal['id']}").status_code == 404
        update = {"name": "Mine now", "servings": 1}
        assert (
            stranger.patch(f"/api/meals/{meal['id']}", json=update).status_code == 404
        )
        assert stranger.delete(f"/api/meals/{meal['id']}").status_code == 404

    assert guest.get(f"/api/meals/{meal['id']}").json()["name"] == "Spaghetti"


# --- Signing up ------------------------------------------------------------------


def test_a_guest_who_signs_up_keeps_their_meals_under_a_new_token(guest):
    guest.post("/api/meals", json={"name": "Spaghetti", "servings": 4})
    guest_token = _token(guest)

    response = _sign_up(guest)

    assert response.status_code == 200, response.text
    body = response.json()
    # The recovery code is in this response only; tests/test_recovery.py.
    assert body.pop("recovery_code")
    assert body == {"email": EMAIL, "is_guest": False, "has_recovery_code": True}
    assert _token(guest) != guest_token
    assert [m["name"] for m in guest.get("/api/meals").json()] == ["Spaghetti"]


def test_the_token_from_before_signing_up_stops_working(guest, anonymous):
    # Session fixation: someone who saw the guest's token must not inherit
    # the account it becomes.
    guest_token = _token(guest)
    _sign_up(guest)

    response = anonymous.get("/api/auth/me", headers=_as(anonymous, guest_token))
    assert response.status_code == 401


def test_signing_up_without_a_session_creates_a_signed_in_account(anonymous):
    response = _sign_up(anonymous)

    assert response.status_code == 200
    assert anonymous.get("/api/auth/me").json() == {
        "email": EMAIL,
        "is_guest": False,
        "has_recovery_code": True,
    }


def test_emails_are_stored_trimmed_and_lower_case(anonymous):
    assert _sign_up(anonymous, email="  Cook@Example.COM ").json()["email"] == EMAIL


def test_an_email_can_only_have_one_account_whatever_its_case(anonymous):
    _sign_up(anonymous)
    with api_client() as someone_else:
        response = _sign_up(someone_else, email="COOK@example.com")

    assert response.status_code == 409
    assert _problem_type(response) == "email-taken"


def test_someone_signed_in_to_an_account_cannot_sign_up_again(anonymous):
    _sign_up(anonymous)
    response = _sign_up(anonymous, email="second@example.com")

    assert response.status_code == 409
    assert _problem_type(response) == "already-signed-up"


@pytest.mark.parametrize(
    ("email", "password", "problem"),
    [
        (EMAIL, "short", "weak-password"),
        (EMAIL, "password1", "weak-password"),
        (EMAIL, EMAIL, "weak-password"),
        ("not-an-email", PASSWORD, "invalid-email"),
        ("cook@localhost", PASSWORD, "invalid-email"),
        ("cook @example.com", PASSWORD, "invalid-email"),
    ],
)
def test_a_rejected_signup_says_why_and_leaves_the_guest_as_it_was(
    guest, email, password, problem
):
    before = _token(guest)
    response = _sign_up(guest, email=email, password=password)

    assert response.status_code == 422
    assert _problem_type(response) == problem
    assert response.json()["detail"]  # a sentence for the person
    assert _token(guest) == before
    assert guest.get("/api/auth/me").json()["is_guest"] is True


# --- Logging in ------------------------------------------------------------------


@pytest.fixture
def account(db):
    """An account exists for EMAIL; the client that made it has logged out."""
    with api_client(as_guest=False) as client:
        _sign_up(client)
        client.post("/api/auth/logout")


def test_the_right_password_signs_in(account, anonymous):
    response = _log_in(anonymous, email="COOK@example.com")

    assert response.status_code == 200
    assert response.json() == {
        "email": EMAIL,
        "is_guest": False,
        "has_recovery_code": True,
    }
    assert anonymous.get("/api/meals").status_code == 200


def test_login_always_issues_a_new_token_and_ends_the_old_session(account, guest):
    guest_token = _token(guest)
    _log_in(guest)

    assert _token(guest) != guest_token
    with api_client(as_guest=False) as other:
        assert (
            other.get("/api/auth/me", headers=_as(other, guest_token)).status_code
            == 401
        )


def test_a_wrong_password_and_an_unknown_email_look_identical(account, anonymous):
    wrong_password = _log_in(anonymous, password="lettuce harbour fork")
    unknown_email = _log_in(anonymous, email="nobody@example.com")

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert _problem_type(response) == "invalid-credentials"
        assert "set-cookie" not in response.headers

    def comparable(response):
        return {k: v for k, v in response.json().items() if k != "instance"}

    assert comparable(wrong_password) == comparable(unknown_email)


def test_a_password_hashed_under_old_parameters_is_upgraded_at_login(
    account, anonymous, db
):
    old_hash = PasswordHasher.from_parameters(profiles.CHEAPEST).hash(PASSWORD)
    with db.transaction() as session:
        user = UserRepository(session).find_by_email(EMAIL)
        assert user is not None
        user.password_hash = old_hash

    assert _log_in(anonymous).status_code == 200

    with db.transaction() as session:
        user = UserRepository(session).find_by_email(EMAIL)
        assert user is not None and user.password_hash is not None
        assert extract_parameters(user.password_hash) == PASSWORD_PARAMETERS


def test_an_account_with_no_password_cannot_be_logged_into(db, anonymous):
    # The unclaimed owner, and guests, have no password: no input matches.
    with db.transaction() as session:
        UserRepository(session).create(is_guest=False)
    assert _log_in(anonymous, email="", password="").status_code in {401, 422}


# --- Logging out -----------------------------------------------------------------


def test_logout_ends_the_session_immediately(guest, db):
    token = _token(guest)
    response = guest.post("/api/auth/logout")

    assert response.status_code == 204
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f'{SESSION_COOKIE}=""') or "max-age=0" in cleared.lower()
    with api_client(as_guest=False) as other:
        assert other.get("/api/auth/me", headers=_as(other, token)).status_code == 401
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sessions")).scalar() == 0


def test_logging_out_twice_is_fine(anonymous):
    assert anonymous.post("/api/auth/logout").status_code == 204


# --- Expiry and refresh ------------------------------------------------------------


START = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _expiry(db: Database) -> datetime:
    with db.engine.connect() as connection:
        value = connection.execute(text("SELECT expires_at FROM sessions")).scalar()
    if isinstance(value, str):  # SQLite returns text
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _at(db: Database, moment: datetime, token: str):
    with db.transaction() as session:
        return AuthService(session, now=moment).authenticate(token)


@pytest.fixture
def started(db: Database) -> str:
    with db.transaction() as session:
        return AuthService(session, now=START).start_guest().token


def test_a_session_ends_thirty_days_after_the_last_visit(db, started):
    with pytest.raises(NotSignedInError):
        _at(db, START + SESSION_LIFETIME + timedelta(minutes=1), started)


def test_a_session_is_still_good_just_before_then(db, started):
    assert _at(db, START + SESSION_LIFETIME - timedelta(minutes=1), started)


def test_a_visit_pushes_the_expiry_back(db, started):
    visit = START + timedelta(days=20)
    _at(db, visit, started)

    assert _expiry(db) == visit + SESSION_LIFETIME
    assert _at(db, START + timedelta(days=45), started)


def test_the_expiry_is_written_at_most_once_an_hour(db, started):
    _at(db, START + REFRESH_INTERVAL - timedelta(minutes=1), started)
    assert _expiry(db) == START + SESSION_LIFETIME, "read-only visit wrote anyway"

    later = START + REFRESH_INTERVAL + timedelta(minutes=1)
    _at(db, later, started)
    assert _expiry(db) == later + SESSION_LIFETIME


def test_the_clock_must_be_timezone_aware(db):
    with db.transaction() as session, pytest.raises(ValueError):
        AuthService(session, now=datetime(2026, 8, 3))


# --- Requests from other websites ------------------------------------------------


def _create(client, **headers):
    return client.post(
        "/api/meals", json={"name": "Spaghetti", "servings": 4}, headers=headers
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://evil.example"},
        {"origin": "null"},
        {"origin": "https://testserver.evil.example"},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
    ],
)
def test_a_write_from_another_website_is_refused(guest, headers):
    response = _create(guest, **headers)

    assert response.status_code == 403
    assert _problem_type(response) == "cross-site-request"
    assert guest.get("/api/meals").json() == []


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://testserver"},  # the app's own page
        {"sec-fetch-site": "same-origin"},
        {},  # not a browser: curl, a script
    ],
)
def test_a_write_from_the_app_itself_is_accepted(guest, headers):
    assert _create(guest, **headers).status_code == 201


def test_logging_in_from_another_website_is_refused_too(account, anonymous):
    # Login CSRF: signing someone into the attacker's account.
    response = anonymous.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_reads_are_not_refused(guest):
    # Reading cannot change anything, and a cross-site page cannot read the
    # response anyway (no CORS grant, and no cookie under SameSite=Strict).
    assert guest.get(
        "/api/meals", headers={"origin": "https://evil.example"}
    ).is_success


def test_a_configured_origin_is_trusted(guest, monkeypatch):
    monkeypatch.setenv("MEAL_PLANNER_CORS_ORIGINS", "https://preview.example")
    assert _create(guest, origin="https://preview.example").status_code == 201


# --- Sample meals for new guests ------------------------------------------------


def test_a_guest_can_start_with_sample_meals_planned_in_their_week(anonymous):
    # A Wednesday: the samples go in the week it falls in.
    response = anonymous.post("/api/auth/guest", json={"sample_week": "2026-08-05"})
    assert response.status_code == 201

    meals = anonymous.get("/api/meals").json()
    assert [m["name"] for m in meals] == [
        "Spaghetti Bolognese",
        "Tacos",
        "Butter Chicken",
    ]
    assert all(m["ingredients"] for m in meals)

    plan = anonymous.get("/api/plan/2026-08-03").json()["days"]
    planned = {d["day"]: d["servings"] for d in plan if d["meal_id"] is not None}
    assert planned == {"Monday": 4, "Tuesday": 2, "Thursday": 4, "Saturday": 2}
    assert anonymous.get("/api/grocery-list/2026-08-03").json()


def test_a_guest_who_asks_for_nothing_starts_empty(guest):
    assert guest.get("/api/meals").json() == []


def test_samples_keep_signing_up_meaningful(anonymous):
    anonymous.post("/api/auth/guest", json={"sample_week": "2026-08-05"})
    _sign_up(anonymous)
    assert len(anonymous.get("/api/meals").json()) == 3
