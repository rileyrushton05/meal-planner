"""Throttling and security events, through the HTTP API.

Networks are simulated the way Vercel reports them: with VERCEL set, the
caller's address is the last entry of `x-vercel-forwarded-for`.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from api_client import api_client
from sqlalchemy import text

from app import events
from app.ratelimit import (
    GUESTS_PER_NETWORK,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_ACCOUNT_AND_NETWORK,
    RATE_LIMIT_KEY_ENV_VAR,
    TAKEN_EMAILS_PER_NETWORK,
    network_of,
    subject,
)
from app.repositories import RateLimitRepository
from server.deps import SESSION_COOKIE
from server.observability import configure_logging

EMAIL = "cook@example.com"
PASSWORD = "lettuce harbour spoon"
WRONG = "lettuce harbour fork"
PER_NETWORK = LOGIN_PER_ACCOUNT_AND_NETWORK.free
PROBLEM = "urn:meal-planner:problem:"


@pytest.fixture
def on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(RATE_LIMIT_KEY_ENV_VAR, "test-only-key")


@pytest.fixture
def account(db):
    with api_client(as_guest=False) as client:
        response = client.post(
            "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200
        client.post("/api/auth/logout")


@pytest.fixture
def anonymous(db):
    with api_client(as_guest=False) as client:
        yield client


@pytest.fixture
def log_lines():
    buffer = io.StringIO()
    configure_logging(stream=buffer, fmt="json")

    def read() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line]

    yield read
    configure_logging()


def _from(network: str | None) -> dict[str, str]:
    return {"x-vercel-forwarded-for": network} if network else {}


def _login(client, password=PASSWORD, *, email=EMAIL, network=None, **headers):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={**_from(network), **headers},
    )


def _type(response) -> str:
    return response.json()["type"].removeprefix(PROBLEM)


# --- Guessing passwords -------------------------------------------------------------


def test_after_five_wrong_passwords_even_the_right_one_must_wait(account, anonymous):
    for _ in range(PER_NETWORK):
        assert _login(anonymous, WRONG).status_code == 401

    response = _login(anonymous)

    assert response.status_code == 429
    assert _type(response) == "too-many-attempts"
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert "1 minute" in response.json()["detail"]
    assert "set-cookie" not in response.headers


def test_a_locked_out_network_does_not_lock_the_owner_out_elsewhere(
    account, anonymous, on_vercel
):
    attacker, owner = "203.0.113.1", "198.51.100.7"
    for _ in range(PER_NETWORK):
        _login(anonymous, WRONG, network=attacker)
    assert _login(anonymous, network=attacker).status_code == 429

    assert _login(anonymous, network=owner).status_code == 200


def test_guesses_spread_across_networks_still_hit_the_account_ceiling(
    account, anonymous, on_vercel
):
    networks = LOGIN_PER_ACCOUNT.free // PER_NETWORK
    for n in range(networks):
        for _ in range(PER_NETWORK):
            assert _login(anonymous, WRONG, network=f"203.0.113.{n}").status_code == 401

    response = _login(anonymous, network="198.51.100.7")
    assert response.status_code == 429


def test_signing_in_clears_the_count(account, anonymous):
    for _ in range(PER_NETWORK - 1):
        _login(anonymous, WRONG)
    assert _login(anonymous).status_code == 200
    anonymous.post("/api/auth/logout")

    for _ in range(PER_NETWORK - 1):
        assert _login(anonymous, WRONG).status_code == 401
    assert _login(anonymous).status_code == 200


def test_an_email_with_no_account_is_throttled_identically(anonymous):
    # Otherwise throttling would answer the question login refuses to.
    for _ in range(PER_NETWORK):
        assert _login(anonymous, WRONG, email="nobody@example.com").status_code == 401
    assert _login(anonymous, email="nobody@example.com").status_code == 429


@pytest.mark.parametrize("rule", [LOGIN_PER_ACCOUNT_AND_NETWORK, LOGIN_PER_ACCOUNT])
def test_a_long_failure_streak_is_recorded_and_still_blocks_login(
    account, anonymous, db, rule
):
    now = datetime.now(UTC)
    parts = ("login", EMAIL)
    if rule == LOGIN_PER_ACCOUNT_AND_NETWORK:
        parts += (network_of("testclient"),)
    key = subject(*parts)
    previous_hits = rule.free + 40
    with db.transaction() as session:
        limits = RateLimitRepository(session)
        limits.get(rule.scope, key, for_update=True)
        limits.save(
            rule.scope,
            key,
            hits=previous_hits,
            window_started_at=now - timedelta(hours=10),
            blocked_until=now - timedelta(seconds=1),
        )

    assert _login(anonymous, WRONG).status_code == 401
    with db.transaction() as session:
        stored = RateLimitRepository(session).get(rule.scope, key)
        assert stored is not None
        assert stored.hits == previous_hits + 1

    response = _login(anonymous)
    assert response.status_code == 429
    assert _type(response) == "too-many-attempts"
    assert 1 <= int(response.headers["retry-after"]) <= 900

    # Once the wait ends, the correct password must still work and clear
    # the entire streak, including a count left by an older deployment.
    with db.transaction() as session:
        RateLimitRepository(session).save(
            rule.scope,
            key,
            hits=previous_hits + 1,
            window_started_at=now - timedelta(hours=10),
            blocked_until=now - timedelta(seconds=1),
        )
    assert _login(anonymous).status_code == 200
    with db.transaction() as session:
        assert RateLimitRepository(session).get(rule.scope, key) is None


def test_a_made_up_forwarding_header_does_not_buy_a_fresh_count(account, anonymous):
    for n in range(PER_NETWORK):
        fake = f"10.0.0.{n}"
        _login(anonymous, WRONG, **{"x-forwarded-for": fake, "x-real-ip": fake})
    assert _login(anonymous, **{"x-forwarded-for": "10.9.9.9"}).status_code == 429


def test_on_vercel_only_the_address_the_platform_appended_counts(
    account, anonymous, on_vercel
):
    for n in range(PER_NETWORK):
        _login(anonymous, WRONG, network=f"10.0.0.{n}, 203.0.113.9")
    assert _login(anonymous, network="10.9.9.9, 203.0.113.9").status_code == 429


def test_counts_survive_the_failed_request_and_store_no_email_or_address(
    account, anonymous, db, on_vercel
):
    # A failed login is an error, and errors roll back; this one keeps the
    # record it made, or nothing would ever be counted.
    _login(anonymous, WRONG, network="203.0.113.9")

    with db.engine.connect() as connection:
        rows = connection.execute(
            text("SELECT scope, subject, hits FROM rate_limits ORDER BY scope")
        ).all()
    assert [(scope, hits) for scope, _, hits in rows] == [
        ("login-account", 1),
        ("login-account-network", 1),
    ]
    for _, stored_subject, _ in rows:
        assert "cook" not in stored_subject and "203.0.113" not in stored_subject


# --- Guests and signups ----------------------------------------------------------


def test_guest_sessions_per_network_are_capped(db, on_vercel):
    with api_client(as_guest=False) as client:
        for _ in range(GUESTS_PER_NETWORK.limit):
            client.cookies.clear()
            response = client.post("/api/auth/guest", headers=_from("203.0.113.9"))
            assert response.status_code == 201
        client.cookies.clear()
        refused = client.post("/api/auth/guest", headers=_from("203.0.113.9"))
        elsewhere = client.post("/api/auth/guest", headers=_from("198.51.100.7"))

    assert refused.status_code == 429
    assert "network" in refused.json()["detail"]
    assert elsewhere.status_code == 201


def test_learning_which_emails_have_accounts_is_capped_per_network(
    account, anonymous, on_vercel
):
    def sign_up(email, network):
        return anonymous.post(
            "/api/auth/signup",
            json={"email": email, "password": PASSWORD},
            headers=_from(network),
        )

    for _ in range(TAKEN_EMAILS_PER_NETWORK.limit):
        assert sign_up(EMAIL, "203.0.113.9").status_code == 409
    assert sign_up(EMAIL, "203.0.113.9").status_code == 429
    assert sign_up("new@example.com", "203.0.113.9").status_code == 429
    assert sign_up("new@example.com", "198.51.100.7").status_code == 200


# --- Security events -------------------------------------------------------------


def _security_events(log_lines) -> list[dict]:
    return [line for line in log_lines() if line["logger"] == "meal_planner.security"]


def test_each_step_of_an_accounts_life_is_a_security_event(anonymous, log_lines):
    anonymous.post("/api/auth/guest")
    anonymous.post("/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    anonymous.post("/api/auth/logout")
    _login(anonymous, WRONG)
    _login(anonymous)
    anonymous.post("/api/auth/logout")

    found = _security_events(log_lines)
    assert [e["event"] for e in found] == [
        "guest_started",
        "signed_up",
        "recovery_code_issued",
        "logged_out",
        "login_failed",
        "logged_in",
        "logged_out",
    ]
    assert found[1]["outcome"] == "guest_upgraded"
    assert all(e["request_id"] for e in found)
    assert found[0]["user_id"] == found[1]["user_id"] == found[2]["user_id"]
    assert found[0]["user_id"] == found[5]["user_id"]


def test_throttling_starting_and_refusing_is_logged(account, anonymous, log_lines):
    for _ in range(PER_NETWORK):
        _login(anonymous, WRONG)
    _login(anonymous)

    found = _security_events(log_lines)
    started = [e for e in found if e["event"] == "login_throttle_started"]
    assert [e["rule"] for e in started] == ["login-account-network"]
    assert started[0]["retry_after_seconds"] == 60
    assert found[-1]["event"] == "throttled"


def test_the_logs_never_hold_a_password_token_email_or_address(
    anonymous, log_lines, on_vercel
):
    network = "203.0.113.77"
    anonymous.post("/api/auth/guest", headers=_from(network))
    guest_token = anonymous.cookies.get(SESSION_COOKIE)
    anonymous.post(
        "/api/auth/signup",
        json={"email": EMAIL, "password": PASSWORD},
        headers=_from(network),
    )
    account_token = anonymous.cookies.get(SESSION_COOKIE)
    anonymous.post("/api/auth/logout", headers=_from(network))
    _login(anonymous, WRONG, network=network)
    _login(anonymous, network=network)
    anonymous.post(
        "/api/meals", json={"name": "x"}, headers={"origin": "https://evil.example"}
    )

    everything = json.dumps(log_lines())
    assert len(_security_events(log_lines)) >= 6
    for secret in (
        PASSWORD,
        WRONG,
        EMAIL,
        "cook@",
        network,
        guest_token,
        account_token,
    ):
        assert secret and secret not in everything, f"{secret!r} reached the logs"


def test_a_refused_cross_site_request_is_logged(anonymous, log_lines):
    anonymous.post("/api/auth/guest")
    anonymous.post(
        "/api/meals", json={"name": "x"}, headers={"origin": "https://evil.example"}
    )

    assert _security_events(log_lines)[-1]["event"] == "cross_site_refused"


def test_an_event_cannot_carry_a_field_nobody_vetted() -> None:
    with pytest.raises(ValueError, match="email"):
        events.record("login_failed", email=EMAIL)
