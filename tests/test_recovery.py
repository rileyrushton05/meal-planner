"""Recovery codes: getting back into an account after forgetting its password.

The gate for this (docs, Phase 2): a code is single-use, never stored or
logged in plaintext, and recovering ends every existing session. Also: the
refusal is the same whether the email or the code is wrong, guesses are
throttled with login, and typing the code is forgiven.
"""

from __future__ import annotations

import io

import pytest
from api_client import api_client
from sqlalchemy import text

from app.ratelimit import LOGIN_PER_ACCOUNT_AND_NETWORK
from app.security import hash_recovery_code
from server.deps import SESSION_COOKIE
from server.observability import configure_logging

EMAIL = "cook@example.com"
PASSWORD = "lettuce harbour spoon"
NEW_PASSWORD = "copper kettle meadow"
PROBLEM = "urn:meal-planner:problem:"
REFUSAL = "That email and recovery code don't match an account."


def _type(response) -> str:
    return response.json()["type"].removeprefix(PROBLEM)


def _recover(client, code: str, *, email: str = EMAIL, password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/recover",
        json={"email": email, "recovery_code": code, "new_password": password},
    )


def _log_in(client, password: str):
    return client.post("/api/auth/login", json={"email": EMAIL, "password": password})


@pytest.fixture
def log_lines():
    buffer = io.StringIO()
    configure_logging(stream=buffer, fmt="json")

    def read() -> str:
        return buffer.getvalue()

    yield read
    configure_logging()


@pytest.fixture
def signed_up(db):
    """An account just made, and the recovery code it was shown."""
    with api_client() as client:
        response = client.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        yield client, response.json()["recovery_code"]


@pytest.fixture
def stranger(db):
    with api_client(as_guest=False) as client:
        yield client


# --- Issuing -----------------------------------------------------------------


def test_signup_shows_a_code_once_and_stores_only_its_hash(signed_up, db) -> None:
    client, code = signed_up

    assert len(code.replace("-", "")) == 16
    with db.engine.connect() as connection:
        stored = connection.execute(
            text("SELECT recovery_code_hash FROM users WHERE email = :e"), {"e": EMAIL}
        ).scalar_one()
    assert stored == hash_recovery_code(code)
    assert code not in stored
    # Not on any later response: it was shown once.
    me = client.get("/api/auth/me").json()
    assert "recovery_code" not in me
    assert me["has_recovery_code"] is True


def test_codes_are_never_logged(db, log_lines) -> None:
    with api_client() as client:
        signup = client.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        )
        first = signup.json()["recovery_code"]
        second = _recover(client, first).json()["recovery_code"]
        third = client.post(
            "/api/account/recovery-code", json={"password": NEW_PASSWORD}
        ).json()["recovery_code"]

    logged = log_lines()
    assert '"recovery_code_issued"' in logged
    for code in (first, second, third):
        assert code not in logged
        assert code.replace("-", "") not in logged


# --- Recovering --------------------------------------------------------------


def test_the_code_sets_a_new_password_and_signs_in(signed_up, stranger) -> None:
    _, code = signed_up

    response = _recover(stranger, code)

    assert response.status_code == 200, response.text
    assert response.json()["email"] == EMAIL
    assert stranger.get("/api/auth/me").json()["email"] == EMAIL
    with api_client(as_guest=False) as browser:
        assert _log_in(browser, PASSWORD).status_code == 401
        assert _log_in(browser, NEW_PASSWORD).status_code == 200


def test_recovering_ends_every_other_session(signed_up, stranger) -> None:
    """Forgotten passwords are not the only reason to replace one: someone
    else may have it, and their browser must not stay signed in."""
    original, code = signed_up
    with api_client(as_guest=False) as other_browser:
        assert _log_in(other_browser, PASSWORD).status_code == 200

        assert _recover(stranger, code).status_code == 200

        assert original.get("/api/auth/me").status_code == 401
        assert other_browser.get("/api/auth/me").status_code == 401
    assert stranger.get("/api/auth/me").status_code == 200


def test_a_code_works_once_and_recovery_hands_out_the_next(signed_up, stranger) -> None:
    _, code = signed_up

    first = _recover(stranger, code)
    again = _recover(stranger, code, password="another fine password")

    assert first.status_code == 200
    assert again.status_code == 401
    assert _type(again) == "invalid-credentials"
    following = first.json()["recovery_code"]
    assert following != code
    assert (
        _recover(stranger, following, password="another fine password").status_code
        == 200
    )


@pytest.mark.parametrize(
    "typed",
    [
        lambda code: code.lower(),
        lambda code: code.replace("-", " "),
        lambda code: code.replace("-", ""),
        lambda code: f"  {code}  ",
        lambda code: code.replace("0", "O").replace("1", "I"),
    ],
    ids=["lower case", "spaces", "no separators", "padded", "letters for digits"],
)
def test_typing_is_forgiven(signed_up, stranger, typed) -> None:
    _, code = signed_up

    assert _recover(stranger, typed(code)).status_code == 200


@pytest.mark.parametrize(
    ("email", "code"),
    [
        (EMAIL, "AAAA-BBBB-CCCC-DDDD"),  # the account, the wrong code
        ("nobody@example.com", None),  # no such account, a real code
    ],
    ids=["wrong code", "unknown email"],
)
def test_the_refusal_says_nothing_about_which_was_wrong(
    signed_up, stranger, email, code
) -> None:
    _, real = signed_up

    response = _recover(stranger, code or real, email=email)

    assert response.status_code == 401
    assert response.json()["detail"] == REFUSAL
    with api_client(as_guest=False) as browser:
        assert _log_in(browser, PASSWORD).status_code == 200


def test_an_account_without_a_code_cannot_be_recovered(db, stranger) -> None:
    """Accounts from before recovery codes have none until they make one;
    an empty hash must never match anything."""
    with api_client() as client:
        client.post("/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE users SET recovery_code_hash = NULL"))

    for code in ("", " ", "-"):
        response = stranger.post(
            "/api/auth/recover",
            json={
                "email": EMAIL,
                "recovery_code": code or "x",
                "new_password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 401


def test_a_weak_new_password_is_refused_and_the_code_still_works(
    signed_up, stranger
) -> None:
    _, code = signed_up

    weak = _recover(stranger, code, password="password1")

    assert weak.status_code == 422
    assert _type(weak) == "weak-password"
    assert _recover(stranger, code).status_code == 200


def test_guessing_codes_is_throttled_with_login(signed_up, stranger) -> None:
    _, code = signed_up
    for _ in range(LOGIN_PER_ACCOUNT_AND_NETWORK.free):
        assert _recover(stranger, "AAAA-BBBB-CCCC-DDDD").status_code == 401

    assert _recover(stranger, code).status_code == 429
    with api_client(as_guest=False) as browser:
        assert _log_in(browser, PASSWORD).status_code == 429


def test_a_guest_who_recovers_their_account_leaves_the_guest_behind(signed_up) -> None:
    _, code = signed_up
    with api_client() as guest:
        guest.post("/api/meals", json={"name": "Guest Toast", "servings": 1})
        guest_token = guest.cookies.get(SESSION_COOKIE)

        assert _recover(guest, code).status_code == 200

        assert guest.get("/api/auth/me").json()["email"] == EMAIL
        assert "Guest Toast" not in guest.get("/api/meals").text
    # The guest's own session ended with it, as at login.
    with api_client(as_guest=False) as browser:
        old = browser.get(
            "/api/auth/me", headers={"cookie": f"{SESSION_COOKIE}={guest_token}"}
        )
        assert old.status_code == 401


# --- Replacing ---------------------------------------------------------------


def test_a_new_code_needs_the_password(signed_up, stranger) -> None:
    client, old = signed_up

    wrong = client.post("/api/account/recovery-code", json={"password": "guess"})

    assert wrong.status_code == 401
    assert _type(wrong) == "invalid-credentials"
    # A refused attempt changes nothing: the old code still works.
    assert _recover(stranger, old).status_code == 200


def test_replacing_retires_the_previous_code(signed_up, stranger) -> None:
    client, old = signed_up

    new = client.post("/api/account/recovery-code", json={"password": PASSWORD}).json()[
        "recovery_code"
    ]

    assert _recover(stranger, old).status_code == 401
    assert _recover(stranger, new).status_code == 200


def test_a_guest_has_no_code_to_replace(db) -> None:
    with api_client() as guest:
        response = guest.post("/api/account/recovery-code", json={"password": "x"})

    assert response.status_code == 409
    assert _type(response) == "no-login"


def test_accounts_from_before_recovery_codes_say_they_have_none(signed_up, db) -> None:
    client, _ = signed_up
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE users SET recovery_code_hash = NULL"))

    assert client.get("/api/auth/me").json()["has_recovery_code"] is False
