"""Throttling: how many attempts are allowed, and how long to wait after.

Two kinds of rule, for two kinds of threat:

- **Backoff**, for guessing passwords. A few free failures, then a wait
  that doubles with each further failure up to a cap, forgotten a day
  after the streak began and cleared by a success. Keyed per account *and*
  network, so someone who knows your email cannot lock you out from their
  own connection, with a higher ceiling per account alone, so spreading
  guesses across many addresses does not escape it either. A browser that
  has signed in to the account before is throttled on its own instead
  (`device_token`), so that ceiling cannot lock the owner out.
- **Window**, for things that are fine in moderation: starting guest
  sessions (each one is a row in the database), learning that an email
  already has an account (which is what signup reveals), and failing to
  sign in to any account at all (one password tried against many emails,
  which no per-account rule sees), and signing up. A fixed number per hour
  per network, and for new accounts one ceiling for everyone, as a
  backstop for many networks at once.

The arithmetic is pure functions of a bucket and the time, so the schedule
is tested exactly, without a clock (tests/test_ratelimit.py). `RateLimiter`
stores buckets through the request's transaction.

Subjects are keyed hashes (HMAC-SHA256) of the email or address, never the
values themselves. The key is `MEAL_PLANNER_RATE_LIMIT_KEY`; without one, a
hash of an IPv4 address could be reversed by hashing all four billion.

An application-level limit cannot stop a distributed attack, and at real
volume this belongs in the platform's firewall or a shared cache. For a
login form, one row per subject in the database the request already uses
costs one statement and nothing to operate.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import os
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.repositories import RateLimitRepository

RATE_LIMIT_KEY_ENV_VAR = "MEAL_PLANNER_RATE_LIMIT_KEY"
_DEVELOPMENT_KEY = "development-only-not-a-secret"


@dataclass(frozen=True, slots=True)
class Bucket:
    hits: int
    window_started_at: datetime
    blocked_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class Backoff:
    """`free` failures, then a wait of `first_wait`, doubling per failure up
    to `max_wait`. The count starts over `forget_after` the streak began."""

    scope: str
    free: int
    first_wait: timedelta
    max_wait: timedelta
    forget_after: timedelta

    def record(self, bucket: Bucket | None, now: datetime) -> Bucket:
        if bucket is None or now - bucket.window_started_at >= self.forget_after:
            bucket = Bucket(hits=0, window_started_at=now)
        hits = bucket.hits + 1
        if hits < self.free:
            return replace(bucket, hits=hits, blocked_until=None)
        # Once doubling would exceed the cap, do not calculate the larger
        # timedelta at all: a long failure streak can overflow it before
        # min() has a chance to apply the cap.
        doublings = hits - self.free
        if doublings >= (self.max_wait // self.first_wait).bit_length():
            wait = self.max_wait
        else:
            wait = self.first_wait * 2**doublings
        return replace(bucket, hits=hits, blocked_until=now + wait)


@dataclass(frozen=True, slots=True)
class Window:
    """At most `limit` per `period`, counted from the first in the period."""

    scope: str
    limit: int
    period: timedelta

    def record(self, bucket: Bucket | None, now: datetime) -> Bucket:
        if bucket is None or now >= bucket.window_started_at + self.period:
            bucket = Bucket(hits=0, window_started_at=now)
        hits = bucket.hits + 1
        blocked = bucket.window_started_at + self.period if hits >= self.limit else None
        return replace(bucket, hits=hits, blocked_until=blocked)


Rule = Backoff | Window


def wait_seconds(wait: timedelta) -> int:
    """Whole seconds, rounded up, never 0: for a Retry-After header."""
    return max(1, math.ceil(wait.total_seconds()))


def describe_wait(wait: timedelta) -> str:
    """'45 seconds', '1 minute', '15 minutes': rounded up, never 'now'."""
    seconds = wait_seconds(wait)
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def wait_remaining(bucket: Bucket | None, now: datetime) -> timedelta | None:
    """How long until the subject may try again, or None if it may now."""
    if bucket is None or bucket.blocked_until is None:
        return None
    remaining = bucket.blocked_until - now
    return remaining if remaining > timedelta(0) else None


# --- The rules ------------------------------------------------------------------

#: Guessing one account's password from one network.
LOGIN_PER_ACCOUNT_AND_NETWORK = Backoff(
    scope="login-account-network",
    free=5,
    first_wait=timedelta(minutes=1),
    max_wait=timedelta(minutes=15),
    forget_after=timedelta(days=1),
)
#: Guessing one account's password from anywhere: higher, so one attacker
#: cannot lock the owner out, but there, so many addresses cannot dodge it.
LOGIN_PER_ACCOUNT = Backoff(
    scope="login-account",
    free=20,
    first_wait=timedelta(minutes=1),
    max_wait=timedelta(minutes=15),
    forget_after=timedelta(days=1),
)
#: Guessing from a browser that has signed in to the account before (see
#: `device_token`), instead of both rules above: the owner's browser is not
#: locked out by guesses made anywhere else, and a stolen device cookie
#: buys no more guesses than one network gets.
LOGIN_PER_DEVICE = Backoff(
    scope="login-device",
    free=5,
    first_wait=timedelta(minutes=1),
    max_wait=timedelta(minutes=15),
    forget_after=timedelta(days=1),
)
#: Failed attempts from one network at any account: trying one common
#: password against many emails, which the per-account rules never see,
#: and each attempt spending the slow password hash. Generous, as a shared
#: connection holds many people's typos; browsers that have signed in
#: before are not counted (or refused) here at all.
LOGIN_FAILURES_PER_NETWORK = Window(
    scope="login-failure-network", limit=50, period=timedelta(hours=1)
)
#: New guest sessions from one network. Generous: a shared connection (a
#: university, an office) can hold many real visitors.
GUESTS_PER_NETWORK = Window(scope="guest-network", limit=30, period=timedelta(hours=1))
#: Signups from one network, a guest's included: each spends the slow
#: password hash, and a new one adds an account for good.
SIGNUPS_PER_NETWORK = Window(
    scope="signup-network", limit=20, period=timedelta(hours=1)
)
#: New accounts, guests and signups alike, from everywhere at once: the
#: backstop for what the per-network rules cannot see, someone with many
#: networks (an IPv6 block holds thousands of /64s). Tripping it turns new
#: visitors away for the rest of the hour, but nobody who already has an
#: account, which is the trade: a full database would turn away everyone.
#: Far above what this app sees, so only a flood reaches it.
NEW_ACCOUNTS_OVERALL = Window(
    scope="new-accounts", limit=300, period=timedelta(hours=1)
)
#: "That email already has an account" answers to one network: what
#: signup reveals, so what an attacker would harvest.
TAKEN_EMAILS_PER_NETWORK = Window(
    scope="taken-email-network", limit=10, period=timedelta(hours=1)
)
#: Recipe imports by one user. Each makes the server fetch a page someone
#: else chose, so the server is not lent out as a crawler.
IMPORTS_PER_USER = Window(
    scope="recipe-import-user", limit=20, period=timedelta(hours=1)
)


# --- Subjects ---------------------------------------------------------------------


def _key() -> bytes:
    configured = os.getenv(RATE_LIMIT_KEY_ENV_VAR)
    if configured:
        return configured.encode()
    if os.getenv("VERCEL"):
        raise RuntimeError(
            f"{RATE_LIMIT_KEY_ENV_VAR} is not set. Throttling hashes emails and "
            "IP addresses with it; set it to a long random value in the "
            "platform's environment settings."
        )
    return _DEVELOPMENT_KEY.encode()


def check_configured() -> None:
    """Raise RuntimeError if the hashing key is missing where it is required
    (on Vercel). For the readiness check, so a deployment missing it says so
    in its health check rather than failing on a visitor's first click."""
    _key()


def network_of(address: str) -> str:
    """The unit a network is throttled by.

    An IPv4 address as it is. An IPv6 address by its /64 prefix: one
    connection is usually given a whole /64, so throttling single IPv6
    addresses would let anyone step through billions of fresh ones.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if parsed.version == 6:
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return str(parsed)


def subject(*parts: str) -> str:
    """A keyed hash of the parts, unambiguous however they are split."""
    message = "\0".join(parts).encode()
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


# --- Devices ---------------------------------------------------------------------
#
# The per-account rule has a cost: anyone who knows an email can reach its
# ceiling, and then the owner is refused too. So a browser that proves the
# password gets a device token, and is throttled on its own from then on
# (OWASP, "Slow Down Online Guessing Attacks with Device Cookies"). It is a
# random id with a keyed hash binding it to the email: nothing to store,
# nothing a stranger can make, and no email in it to read. It is not a
# credential: it only decides which throttle applies.

_DEVICE_ID_BYTES = 16
_MAX_DEVICE_TOKEN_LENGTH = 128


def device_token(email_key: str) -> str:
    """A new token for the browser that just proved it holds the account
    for `email_key` (trimmed and lower-cased, as login compares it)."""
    device = secrets.token_urlsafe(_DEVICE_ID_BYTES)
    return f"{device}.{subject('device', email_key, device)}"


def trusted_device(token: str | None, email_key: str) -> str | None:
    """The device's id if `token` was issued for `email_key`, else None:
    missing, made up, or given for another account."""
    if not token or len(token) > _MAX_DEVICE_TOKEN_LENGTH:
        return None
    device, _, mac = token.partition(".")
    if not device or not mac:
        return None
    expected = subject("device", email_key, device)
    return device if hmac.compare_digest(mac.encode(), expected.encode()) else None


# --- Storage ---------------------------------------------------------------------


class RateLimiter:
    """Rules applied to stored buckets, within the request's transaction."""

    def __init__(self, session: Session, *, now: datetime) -> None:
        self._buckets = RateLimitRepository(session)
        self._now = now

    def wait_remaining(self, rule: Rule, subject: str) -> timedelta | None:
        return wait_remaining(self._load(rule, subject), self._now)

    def record(self, rule: Rule, subject: str) -> Bucket:
        """Count one attempt. The row is locked first, so two attempts at
        once are both counted rather than both reading the same total."""
        updated = rule.record(self._load(rule, subject, for_update=True), self._now)
        self._buckets.save(
            rule.scope,
            subject,
            hits=updated.hits,
            window_started_at=updated.window_started_at,
            blocked_until=updated.blocked_until,
        )
        return updated

    def clear(self, rule: Rule, subject: str) -> None:
        self._buckets.delete(rule.scope, subject)

    def _load(
        self, rule: Rule, subject: str, *, for_update: bool = False
    ) -> Bucket | None:
        row = self._buckets.get(rule.scope, subject, for_update=for_update)
        if row is None:
            return None
        return Bucket(
            hits=row.hits,
            window_started_at=_as_utc(row.window_started_at),
            blocked_until=_as_utc(row.blocked_until) if row.blocked_until else None,
        )


def _as_utc(moment: datetime) -> datetime:
    """SQLite hands timestamps back without a zone; they were stored as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


#: A bucket whose window began longer ago than this cannot refuse or count
#: anything any more: every rule forgets or starts over within it. The
#: purge job deletes such buckets.
STALE_AFTER = max(
    LOGIN_PER_ACCOUNT_AND_NETWORK.forget_after,
    LOGIN_PER_ACCOUNT.forget_after,
    LOGIN_PER_DEVICE.forget_after,
    LOGIN_FAILURES_PER_NETWORK.period,
    GUESTS_PER_NETWORK.period,
    SIGNUPS_PER_NETWORK.period,
    NEW_ACCOUNTS_OVERALL.period,
    TAKEN_EMAILS_PER_NETWORK.period,
    IMPORTS_PER_USER.period,
)
