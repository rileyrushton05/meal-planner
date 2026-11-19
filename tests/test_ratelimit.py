"""The throttling schedule, as pure arithmetic over a bucket and a time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import ratelimit
from app.ratelimit import (
    GUESTS_PER_NETWORK,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_ACCOUNT_AND_NETWORK,
    Backoff,
    Bucket,
    Window,
    network_of,
    subject,
    wait_remaining,
)

T0 = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
RULE = Backoff(
    scope="test",
    free=5,
    first_wait=timedelta(minutes=1),
    max_wait=timedelta(minutes=15),
    forget_after=timedelta(days=1),
)


def _fail(times: int, rule=RULE, *, at=T0, bucket=None):
    for _ in range(times):
        bucket = rule.record(bucket, at)
    return bucket


# --- Backoff -----------------------------------------------------------------------


def test_the_first_four_failures_are_free() -> None:
    bucket = _fail(4)
    assert bucket.hits == 4
    assert wait_remaining(bucket, T0) is None


@pytest.mark.parametrize(
    ("failures", "minutes"),
    [(5, 1), (6, 2), (7, 4), (8, 8), (9, 15), (12, 15)],
)
def test_the_wait_doubles_from_the_fifth_failure_up_to_a_cap(failures, minutes):
    assert wait_remaining(_fail(failures), T0) == timedelta(minutes=minutes)


def test_the_wait_runs_out() -> None:
    bucket = _fail(5)
    assert wait_remaining(bucket, T0 + timedelta(seconds=59)) == timedelta(seconds=1)
    assert wait_remaining(bucket, T0 + timedelta(minutes=1)) is None


def test_failures_are_forgotten_a_day_after_the_streak_began() -> None:
    bucket = _fail(4)
    tomorrow = T0 + timedelta(days=1)
    bucket = RULE.record(bucket, tomorrow)
    assert bucket.hits == 1
    assert bucket.window_started_at == tomorrow


@pytest.mark.parametrize("rule", [LOGIN_PER_ACCOUNT_AND_NETWORK, LOGIN_PER_ACCOUNT])
def test_a_day_of_spaced_failures_keeps_the_wait_capped(rule: Backoff) -> None:
    now = T0
    bucket = None
    for _ in range(75):
        bucket = rule.record(bucket, now)
        wait = wait_remaining(bucket, now)
        assert wait is None or wait <= rule.max_wait
        now += (wait or timedelta(0)) + timedelta(seconds=1)

    assert bucket.hits == 75
    assert now < T0 + rule.forget_after
    assert bucket.blocked_until == now - timedelta(seconds=1)
    reset = rule.record(bucket, T0 + rule.forget_after)
    assert reset.hits == 1
    assert reset.blocked_until is None


@pytest.mark.parametrize("rule", [LOGIN_PER_ACCOUNT_AND_NETWORK, LOGIN_PER_ACCOUNT])
def test_a_large_stored_failure_count_still_uses_the_maximum_wait(
    rule: Backoff,
) -> None:
    bucket = Bucket(hits=1000, window_started_at=T0)
    updated = rule.record(bucket, T0)
    assert updated.hits == bucket.hits + 1
    assert wait_remaining(updated, T0) == rule.max_wait


def test_the_account_ceiling_is_higher_than_the_per_network_limit() -> None:
    assert LOGIN_PER_ACCOUNT.free > LOGIN_PER_ACCOUNT_AND_NETWORK.free
    assert wait_remaining(_fail(19, LOGIN_PER_ACCOUNT), T0) is None
    assert wait_remaining(_fail(20, LOGIN_PER_ACCOUNT), T0) == timedelta(minutes=1)


# --- Window ------------------------------------------------------------------------

HOURLY = Window(scope="test", limit=3, period=timedelta(hours=1))


def test_a_window_allows_its_limit_then_blocks_until_it_ends() -> None:
    bucket = None
    for minute in (0, 10):
        bucket = HOURLY.record(bucket, T0 + timedelta(minutes=minute))
        assert wait_remaining(bucket, T0 + timedelta(minutes=minute)) is None

    bucket = HOURLY.record(bucket, T0 + timedelta(minutes=20))
    # Blocked until an hour after the first, not after the last.
    assert wait_remaining(bucket, T0 + timedelta(minutes=20)) == timedelta(minutes=40)


def test_a_new_window_starts_fresh() -> None:
    bucket = None
    for _ in range(3):
        bucket = HOURLY.record(bucket, T0)
    bucket = HOURLY.record(bucket, T0 + timedelta(hours=1))
    assert (bucket.hits, wait_remaining(bucket, T0 + timedelta(hours=1))) == (1, None)


def test_the_guest_limit_allows_a_shared_network_some_room() -> None:
    assert GUESTS_PER_NETWORK.limit >= 20


# --- Subjects and networks ------------------------------------------------------------


def test_a_subject_hides_what_it_was_made_from() -> None:
    made = subject("login", "cook@example.com", "203.0.113.9")
    assert len(made) == 64
    assert "cook" not in made and "203" not in made


def test_subjects_are_unambiguous_however_the_parts_split() -> None:
    assert subject("ab", "c") != subject("a", "bc")


def test_subjects_depend_on_the_secret_key(monkeypatch) -> None:
    before = subject("network", "203.0.113.9")
    monkeypatch.setenv(ratelimit.RATE_LIMIT_KEY_ENV_VAR, "another-secret")
    assert subject("network", "203.0.113.9") != before


def test_a_deployment_without_a_key_fails_loudly(monkeypatch) -> None:
    monkeypatch.delenv(ratelimit.RATE_LIMIT_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match=ratelimit.RATE_LIMIT_KEY_ENV_VAR):
        subject("network", "203.0.113.9")


@pytest.mark.parametrize(
    ("address", "network"),
    [
        ("203.0.113.9", "203.0.113.9"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("testclient", "testclient"),
    ],
)
def test_ipv6_addresses_are_throttled_by_their_slash_64(address, network) -> None:
    assert network_of(address) == network
