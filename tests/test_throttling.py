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
    LOGIN_FAILURES_PER_NETWORK,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_ACCOUNT_AND_NETWORK,
    NEW_ACCOUNTS_OVERALL,
    RATE_LIMIT_KEY_ENV_VAR,
    SIGNUPS_PER_NETWORK,
    TAKEN_EMAILS_PER_NETWORK,
    network_of,
    subject,
)
from app.repositories import RateLimitRepository
from server.deps import DEVICE_COOKIE, SESSION_COOKIE
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


# --- Browsers that have signed in before ------------------------------------------
#
# The account-wide ceiling is reached by anyone who knows the email, from a
# few networks, in seconds. A browser that has proven the password before
# carries a device cookie, and is throttled on its own instead, so the
# owner's own browser is not locked out (OWASP's "device cookies").


@pytest.fixture
def owners_browser(account):
    """A browser the owner has signed in from before, then signed out."""
    with api_client(as_guest=False) as browser:
        assert _login(browser).status_code == 200
        browser.post("/api/auth/logout")
        yield browser


def _set_cookie(client, name: str, value: str) -> None:
    # Where the test client keeps cookies the server set (http.cookiejar
    # names a dotless host "<host>.local"), so this one replaces theirs.
    client.cookies.set(name, value, domain="testserver.local", path="/")


def _changed(text: str) -> str:
    """`text` with its last character replaced by a different one."""
    return text[:-1] + ("b" if text[-1] == "a" else "a")


def _lock_the_account(client) -> None:
    networks = LOGIN_PER_ACCOUNT.free // PER_NETWORK
    for n in range(networks):
        for _ in range(PER_NETWORK):
            _login(client, WRONG, network=f"203.0.113.{n}")
    assert _login(client, network="198.51.100.7").status_code == 429


def test_guesses_elsewhere_do_not_lock_out_a_browser_that_signed_in_before(
    on_vercel, owners_browser, anonymous
):
    _lock_the_account(anonymous)

    assert _login(owners_browser, network="198.51.100.7").status_code == 200
    owners_browser.post("/api/auth/logout")
    # Even from the network the guesses came from.
    assert _login(owners_browser, network="203.0.113.0").status_code == 200


def test_a_trusted_browser_guessing_is_throttled_on_its_own(owners_browser, anonymous):
    for _ in range(PER_NETWORK):
        assert _login(owners_browser, WRONG).status_code == 401
    assert _login(owners_browser).status_code == 429

    # Its guesses were not counted against anyone else.
    assert _login(anonymous).status_code == 200


def test_the_device_cookie_vouches_only_for_its_own_account(
    on_vercel, owners_browser, anonymous
):
    other = "other@example.com"
    with api_client(as_guest=False) as theirs:
        theirs.post("/api/auth/signup", json={"email": other, "password": PASSWORD})
    networks = LOGIN_PER_ACCOUNT.free // PER_NETWORK
    for n in range(networks):
        for _ in range(PER_NETWORK):
            _login(anonymous, WRONG, email=other, network=f"203.0.113.{n}")

    response = _login(owners_browser, email=other, network="198.51.100.7")

    assert response.status_code == 429


def test_a_made_up_device_cookie_vouches_for_nothing(
    on_vercel, owners_browser, anonymous
):
    genuine = owners_browser.cookies[DEVICE_COOKIE]
    device, _, mac = genuine.partition(".")
    _lock_the_account(anonymous)
    with api_client(as_guest=False) as forger:
        for forged in (
            "x",
            "x.y",
            ".",
            f"{device}.",
            f"{device}.{_changed(mac)}",
            f"{_changed(device)}.{mac}",
            genuine + "x" * 200,
        ):
            _set_cookie(forger, DEVICE_COOKIE, forged)
            assert _login(forger, network="198.51.100.7").status_code == 429

        # The cookie set this way is sent: the genuine one gets in.
        _set_cookie(forger, DEVICE_COOKIE, genuine)
        assert _login(forger, network="198.51.100.7").status_code == 200


def test_the_device_cookie_is_locked_down_and_holds_no_email(account):
    with api_client(as_guest=False) as browser:
        response = _login(browser)
        cookie = next(
            c
            for c in response.headers.get_list("set-cookie")
            if c.startswith(f"{DEVICE_COOKIE}=")
        )
        value = browser.cookies.get(DEVICE_COOKIE)
        browser.post("/api/auth/logout")
        kept = browser.cookies.get(DEVICE_COOKIE)

    attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert {"httponly", "secure", "path=/", "samesite=strict"} <= attributes
    assert not any(a.startswith("domain") for a in attributes)
    assert value and "cook" not in value and "example" not in value
    # Signing out does not forget that this browser is the owner's.
    assert kept == value


def test_signing_up_or_recovering_also_makes_the_browser_trusted(anonymous):
    response = anonymous.post(
        "/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}
    )
    assert anonymous.cookies.get(DEVICE_COOKIE)
    code = response.json()["recovery_code"]
    with api_client(as_guest=False) as other:
        other.post(
            "/api/auth/recover",
            json={
                "email": EMAIL,
                "recovery_code": code,
                "new_password": "copper kettle meadow",
            },
        )
        assert other.cookies.get(DEVICE_COOKIE)


def test_a_guest_gets_no_device_cookie(anonymous):
    assert anonymous.post("/api/auth/guest").status_code == 201
    assert anonymous.cookies.get(DEVICE_COOKIE) is None


def test_deleting_the_account_forgets_the_browser(account):
    with api_client(as_guest=False) as browser:
        _login(browser)
        response = browser.request(
            "DELETE", "/api/account", json={"password": PASSWORD}
        )
        assert response.status_code == 204
        assert browser.cookies.get(DEVICE_COOKIE) is None


# --- One password against many accounts -------------------------------------------


def _spray(client, network: str, attempts: int) -> list[int]:
    return [
        _login(
            client, WRONG, email=f"person{n}@example.com", network=network
        ).status_code
        for n in range(attempts)
    ]


def test_one_network_failing_against_many_emails_is_capped(
    account, anonymous, on_vercel
):
    limit = LOGIN_FAILURES_PER_NETWORK.limit
    assert set(_spray(anonymous, "203.0.113.9", limit)) == {401}

    refused = _login(anonymous, network="203.0.113.9")

    assert refused.status_code == 429
    assert "network" in refused.json()["detail"]
    assert _login(anonymous, network="198.51.100.7").status_code == 200


def test_failed_recoveries_count_towards_the_same_cap(account, anonymous, on_vercel):
    limit = LOGIN_FAILURES_PER_NETWORK.limit
    for n in range(limit):
        anonymous.post(
            "/api/auth/recover",
            json={
                "email": f"person{n}@example.com",
                "recovery_code": "AAAA-BBBB-CCCC-DDDD",
                "new_password": "copper kettle meadow",
            },
            headers=_from("203.0.113.9"),
        )

    assert _login(anonymous, network="203.0.113.9").status_code == 429


def test_signing_in_does_not_reset_the_count_across_emails(
    account, anonymous, on_vercel
):
    limit = LOGIN_FAILURES_PER_NETWORK.limit
    with api_client(as_guest=False) as sprayer:
        _spray(sprayer, "203.0.113.9", limit - 1)
        # The sprayer's own account, in a browser not yet trusted for it.
        assert _login(sprayer, network="203.0.113.9").status_code == 200
        sprayer.post("/api/auth/logout")
        sprayer.cookies.clear()
        _spray(sprayer, "203.0.113.9", 1)

        assert _login(sprayer, network="203.0.113.9").status_code == 429


def test_a_trusted_browser_is_not_refused_with_its_network(
    on_vercel, owners_browser, anonymous
):
    _spray(anonymous, "203.0.113.9", LOGIN_FAILURES_PER_NETWORK.limit)

    assert _login(owners_browser, network="203.0.113.9").status_code == 200


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
    logins = [(scope, hits) for scope, _, hits in rows if scope.startswith("login")]
    assert logins == [
        ("login-account", 1),
        ("login-account-network", 1),
        ("login-failure-network", 1),
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


def _sign_up(client, email: str, network: str):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD},
        headers=_from(network),
    )


def test_signups_per_network_are_capped(db, on_vercel):
    # Each spends the slow password hash, and most add an account for good.
    for n in range(SIGNUPS_PER_NETWORK.limit):
        # Half from guests upgrading, half straight to an account.
        with api_client(as_guest=False) as browser:
            if n % 2:
                browser.post("/api/auth/guest", headers=_from("203.0.113.9"))
            response = _sign_up(browser, f"person{n}@example.com", "203.0.113.9")
            assert response.status_code == 200, response.text

    with api_client(as_guest=False) as browser:
        refused = _sign_up(browser, "one-more@example.com", "203.0.113.9")
        elsewhere = _sign_up(browser, "one-more@example.com", "198.51.100.7")

    assert refused.status_code == 429
    assert "network" in refused.json()["detail"]
    assert elsewhere.status_code == 200


def _overall_count(db) -> int:
    with db.transaction() as session:
        row = RateLimitRepository(session).get(
            NEW_ACCOUNTS_OVERALL.scope, subject("everyone")
        )
        return row.hits if row is not None else 0


def test_every_new_account_counts_towards_the_overall_ceiling(db, on_vercel):
    with api_client(as_guest=False) as browser:
        browser.post("/api/auth/guest", headers=_from("203.0.113.1"))
        # Upgrading the guest adds no account: its row already exists.
        _sign_up(browser, "guest@example.com", "203.0.113.1")
    with api_client(as_guest=False) as browser:
        _sign_up(browser, "direct@example.com", "203.0.113.2")

    assert _overall_count(db) == 2


def test_at_the_overall_ceiling_only_new_visitors_are_turned_away(
    on_vercel, account, db
):
    with api_client(as_guest=False) as guest:
        assert guest.post("/api/auth/guest").status_code == 201
        now = datetime.now(UTC)
        with db.transaction() as session:
            limits = RateLimitRepository(session)
            limits.get(NEW_ACCOUNTS_OVERALL.scope, subject("everyone"), for_update=True)
            limits.save(
                NEW_ACCOUNTS_OVERALL.scope,
                subject("everyone"),
                hits=NEW_ACCOUNTS_OVERALL.limit,
                window_started_at=now,
                blocked_until=now + NEW_ACCOUNTS_OVERALL.period,
            )

        with api_client(as_guest=False) as newcomer:
            new_guest = newcomer.post("/api/auth/guest", headers=_from("198.51.100.7"))
            new_account = _sign_up(newcomer, "new@example.com", "198.51.100.8")
            assert new_guest.status_code == new_account.status_code == 429
            assert "new visitors" in new_guest.json()["detail"]
            # Someone with an account still gets in,
            assert _login(newcomer).status_code == 200
        # and a guest already here can still keep what they made.
        assert _sign_up(guest, "guest@example.com", "198.51.100.9").status_code == 200


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
