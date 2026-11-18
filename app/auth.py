"""Accounts and sessions: guests, signup, login, logout, and who is asking.

No HTTP here. The routes in server/routers/auth.py move tokens in and out
of cookies; everything that decides who someone is lives in this module,
with the clock passed in so expiry and refresh can be tested exactly.

The rules, and why:

- **A session is a random token in a cookie**, stored only as its SHA-256
  (app/security.py). Database sessions rather than signed tokens, so a
  session can actually be revoked: logout deletes the row.
- **The token changes whenever who you are changes**: at login, and when a
  guest signs up. Otherwise a token captured before signup (on a shared
  computer, say) would carry into the new account. This is the defence
  against session fixation.
- **Sessions expire after 30 days without a visit.** A visit pushes the
  expiry back, but at most once an hour, so ordinary reads are not writes.
- **Login never says which half was wrong**, and costs the same time either
  way (`verify_password`), so it cannot be used to discover who has an
  account. Signup, unavoidably, says an email is taken; how often one
  network may hear that is limited. Signup forms that send a verification
  email can avoid saying it; this app sends no email at all (recovery is by
  code, below), so the limit is the defence.
- **Guessing is throttled** (app/ratelimit.py): per account and network,
  with a higher ceiling per account. While throttled, even the right
  password is refused, without being checked.
- **A forgotten password is recovered with a code**, shown once at signup
  and stored only as a hash, rather than a link sent by email: no third
  party receives anyone's address. Each code works once, and recovering
  ends every session. Guesses share login's throttle.
- **Each of these is a security event** (app/events.py).
"""

from __future__ import annotations

import hmac
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session

from app import events
from app.db import act_as
from app.exceptions import (
    AlreadySignedUpError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    NoLoginError,
    NotSignedInError,
    TooManyAttemptsError,
)
from app.models import User, persisted_id
from app.ratelimit import (
    GUESTS_PER_NETWORK,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_ACCOUNT_AND_NETWORK,
    TAKEN_EMAILS_PER_NETWORK,
    RateLimiter,
    Rule,
    network_of,
    subject,
)
from app.repositories import SessionRepository, UserRepository
from app.samples import add_samples
from app.security import (
    check_password_policy,
    hash_password,
    hash_recovery_code,
    hash_session_token,
    needs_rehash,
    new_recovery_code,
    new_session_token,
    verify_password,
)

#: How long a session survives without a visit.
SESSION_LIFETIME = timedelta(days=30)
#: How stale an expiry may get before a visit pushes it back. Without this,
#: every request, reads included, would write to the sessions table.
REFRESH_INTERVAL = timedelta(hours=1)

MAX_EMAIL_LENGTH = 254


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Who a request is from, as established from its session cookie."""

    id: int
    email: str | None
    is_guest: bool
    #: Identifies the session itself, so logout and token rotation can end it.
    token_hash: str
    #: Whether the account can be recovered if its password is forgotten.
    has_recovery_code: bool = False


@dataclass(frozen=True, slots=True)
class SignedIn:
    """The result of starting a session: the account, and the new token the
    caller must put in the cookie. The token exists nowhere else."""

    user: CurrentUser
    token: str
    #: A new recovery code, when one was just issued (signup, recovery). Like
    #: the token, it exists nowhere else: show it once.
    recovery_code: str | None = None


def normalise_email(raw: str) -> str:
    """Trimmed, lower-cased, and checked to be shaped like an address.

    Deliberately loose: the only real test of an address is sending to it,
    and the app never does (it is a login name; recovery is by code). This
    catches typos such as a missing @, not unusual but valid addresses.
    """
    email = raw.strip().lower()
    local, at, domain = email.rpartition("@")
    if (
        not at
        or not local
        or len(email) > MAX_EMAIL_LENGTH
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or any(character.isspace() for character in email)
    ):
        raise InvalidEmailError("Enter an email address like name@example.com.")
    return email


class AuthService:
    """Account operations within one transaction, at one moment in time,
    for a request from one network (its IP address, or "unknown")."""

    def __init__(
        self, session: Session, *, now: datetime, address: str = "unknown"
    ) -> None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        self._session = session
        self._users = UserRepository(session)
        self._sessions = SessionRepository(session)
        self._limits = RateLimiter(session, now=now)
        self._now = now
        self._network = network_of(address)

    # --- Who is asking ------------------------------------------------------

    def authenticate(self, token: str | None) -> CurrentUser:
        """The user a session cookie belongs to. Raises NotSignedInError.

        A missing, unknown, tampered or expired token all look the same to
        the caller: not signed in.
        """
        if not token:
            raise NotSignedInError("Sign in, or continue as a guest, to do that.")
        token_hash = hash_session_token(token)
        found = self._sessions.find_live(token_hash, self._now)
        if found is None:
            raise NotSignedInError(
                "Your session has ended. Sign in again, or continue as a guest."
            )
        row, user = found

        if _as_utc(row.expires_at) - self._now < SESSION_LIFETIME - REFRESH_INTERVAL:
            self._sessions.extend(token_hash, self._now + SESSION_LIFETIME)
            self._users.touch(persisted_id(user), self._now)

        return _current(user, token_hash)

    # --- Starting and ending sessions ---------------------------------------

    def start_guest(self, sample_week: date | None = None) -> SignedIn:
        """A new account with no credentials, and a session for it.

        With `sample_week`, the account starts with sample meals planned in
        that week (app/samples.py), so the first screen has something on it.
        """
        network = subject("network", self._network)
        self._refuse_if_throttled(
            GUESTS_PER_NETWORK,
            network,
            "Too many new sessions have started from your network. "
            "Try again in {wait}.",
        )
        user = self._users.create(is_guest=True)
        self._limits.record(GUESTS_PER_NETWORK, network)
        if sample_week is not None:
            # From here the transaction acts as the new guest, so the
            # samples are written through row-level security like any other
            # of their writes.
            act_as(self._session, persisted_id(user))
            add_samples(self._session, persisted_id(user), sample_week)
        events.record("guest_started", user_id=persisted_id(user))
        return self._start_session(user)

    def sign_up(
        self, current: CurrentUser | None, email: str, password: str
    ) -> SignedIn:
        """Create an account, or turn the caller's guest account into one.

        A guest keeps the same row, so every meal and plan they made comes
        with them; only the session token changes.
        """
        if current is not None and not current.is_guest:
            raise AlreadySignedUpError(
                "You're already signed in to an account. Log out to create another."
            )
        network = subject("network", self._network)
        self._refuse_if_throttled(
            TAKEN_EMAILS_PER_NETWORK,
            network,
            "Too many signup attempts from your network. Try again in {wait}.",
        )
        try:
            email, password_hash = self._new_credentials(email, password)
        except EmailTakenError:
            # Keeps writes: the only thing written so far is this record
            # (and perhaps a session refresh), which must outlive the error.
            self._limits.record(TAKEN_EMAILS_PER_NETWORK, network)
            events.record("signup_email_taken", subject=network)
            raise

        if current is None:
            user = self._users.create_account(email, password_hash)
            outcome = "account_created"
        else:
            user = self._users.get(current.id)
            if user is None:  # pragma: no cover - authenticate just found it
                raise NotSignedInError("Your session has ended.")
            self._users.set_credentials(user, email, password_hash)
            self._sessions.delete(current.token_hash)
            outcome = "guest_upgraded"
        events.record("signed_up", user_id=persisted_id(user), outcome=outcome)
        code = self._issue_recovery_code(user)
        return self._start_session(user, recovery_code=code)

    def claim(self, user_id: int, email: str, password: str) -> None:
        """Give the unclaimed owner (the account holding the data from before
        accounts existed) an email and password. For `app.cli`, run by
        whoever deploys; through the same checks as signing up.
        """
        user = self._users.get(user_id)
        if user is None or user.is_guest or user.email is not None:
            raise ValueError(f"User {user_id} is not an unclaimed account.")
        email, password_hash = self._new_credentials(email, password)
        self._users.set_credentials(user, email, password_hash)
        events.record("account_claimed", user_id=user_id)

    def set_password(self, user_id: int, password: str) -> int:
        """Replace an account's password and end all of its sessions,
        returning how many were ended. For `app.cli`, run by whoever deploys:
        the way back for someone who has lost both their password and their
        recovery code.

        Every session goes, because a new password is often the answer to
        "someone else may have it": a browser signed in with the old one
        must not stay signed in.
        """
        user = self._users.get(user_id)
        if user is None or user.email is None:
            raise ValueError(f"User {user_id} is not an account with a login.")
        check_password_policy(password, email=user.email)
        self._users.set_password_hash(user, hash_password(password))
        ended = self._sessions.delete_all_for(user_id)
        events.record("password_set", user_id=user_id, removed={"sessions": ended})
        return ended

    def log_in(
        self, current: CurrentUser | None, email: str, password: str
    ) -> SignedIn:
        """Start a session for the account with these credentials.

        Raises InvalidCredentialsError, with the same message and the same
        cost whether the email is unknown or the password is wrong, and
        TooManyAttemptsError while throttled. Throttling is keyed on the
        email as typed, account or not, so it reveals nothing either.
        """
        email_key = email.strip().lower()
        user = self._check_password(
            email_key,
            self._users.find_by_email(email_key),
            password,
            refusal="That email and password don't match an account.",
        )
        # Hashes made under older parameters are upgraded now, the one time
        # the password is in hand.
        if user.password_hash is not None and needs_rehash(user.password_hash):
            self._users.set_password_hash(user, hash_password(password))

        # A new token, never the one presented: this is where session
        # fixation is stopped. A guest who logs in leaves their guest data
        # behind, to be cleaned up with the guest.
        if current is not None:
            self._sessions.delete(current.token_hash)
        events.record("logged_in", user_id=persisted_id(user))
        return self._start_session(user)

    def log_out(self, current: CurrentUser) -> None:
        self._sessions.delete(current.token_hash)
        events.record("logged_out", user_id=current.id)

    # --- Leaving ------------------------------------------------------------------

    def delete_account(
        self, current: CurrentUser, password: str | None
    ) -> dict[str, int]:
        """Delete the account and everything in it, for good, returning how
        many rows of each kind went.

        An account with a login must give its password again: a session left
        open on a shared computer, or stolen, should not be enough to destroy
        an account. Wrong guesses here count against the same throttle as
        login, so this cannot be used to guess the password either. A guest
        has no password, and nothing to lose that their session does not
        already reach.
        """
        user = self._users.get(current.id)
        if user is None:
            raise NotSignedInError("Your session has ended. Sign in again.")
        if user.email is not None:
            self._check_password(
                user.email,
                user,
                password or "",
                refusal="That password isn't right.",
                outcome="delete_account",
            )
        # The counts read tables under row security, which shows a user only
        # their own rows once the transaction says whose they are.
        act_as(self._session, current.id)
        removed = self._users.delete_with_everything(current.id)
        events.record("account_deleted", user_id=current.id, removed=removed)
        return removed

    # --- Recovery codes -------------------------------------------------------------

    def replace_recovery_code(self, current: CurrentUser, password: str) -> str:
        """A new recovery code for the account, confirmed with its password;
        the old one stops working. For a code lost, or never made (accounts
        from before recovery codes)."""
        user = self._users.get(current.id)
        if user is None:
            raise NotSignedInError("Your session has ended. Sign in again.")
        if user.email is None:
            raise NoLoginError(
                "A guest session has no password to recover. Sign up first."
            )
        self._check_password(
            user.email,
            user,
            password,
            refusal="That password isn't right.",
            outcome="replace_recovery_code",
        )
        return self._issue_recovery_code(user)

    def recover(
        self,
        current: CurrentUser | None,
        email: str,
        recovery_code: str,
        new_password: str,
    ) -> SignedIn:
        """Set a new password with the email and recovery code, for someone
        who has forgotten theirs. Signs them in, with a new recovery code.

        The code is single-use: a new one replaces it, which is the only
        copy the person now has. Every existing session ends, as with any
        new password: the reason for it may be someone else having the old
        one. The refusal is the same whether the email or the code is wrong,
        and guesses are throttled with login.
        """
        email_key = email.strip().lower()
        # First, and checked for anyone: it says nothing about the account.
        check_password_policy(new_password, email=email_key)
        presented = hash_recovery_code(recovery_code)

        def matches(found: User | None) -> bool:
            stored = found.recovery_code_hash if found is not None else None
            # Compared even when there is nothing to compare with, so the
            # time taken does not say whether the email has an account.
            same = hmac.compare_digest(stored or "", presented)
            return same and stored is not None

        user = self._prove(
            email_key,
            self._users.find_by_email(email_key),
            matches,
            refusal="That email and recovery code don't match an account.",
            outcome="recover",
        )
        user_id = persisted_id(user)
        self._users.set_password_hash(user, hash_password(new_password))
        ended = self._sessions.delete_all_for(user_id)
        if current is not None and current.id != user_id:
            # A guest recovering their account leaves the guest behind, as
            # at login, to be cleaned up with other idle guests.
            self._sessions.delete(current.token_hash)
        events.record(
            "password_recovered", user_id=user_id, removed={"sessions": ended}
        )
        code = self._issue_recovery_code(user)
        return self._start_session(user, recovery_code=code)

    # --- Helpers ---------------------------------------------------------------

    def _issue_recovery_code(self, user: User) -> str:
        code = new_recovery_code()
        self._users.set_recovery_code_hash(user, hash_recovery_code(code))
        events.record("recovery_code_issued", user_id=persisted_id(user))
        return code

    def _check_password(
        self,
        email_key: str,
        user: User | None,
        password: str,
        *,
        refusal: str,
        outcome: str | None = None,
    ) -> User:
        """Return `user` if `password` is theirs, or refuse (see `_prove`).

        `verify_password` costs the same with no user, so a refusal takes
        as long whether or not the email has an account.
        """
        return self._prove(
            email_key,
            user,
            lambda found: verify_password(
                found.password_hash if found is not None else None, password
            ),
            refusal=refusal,
            outcome=outcome,
        )

    def _prove(
        self,
        email_key: str,
        user: User | None,
        proven: Callable[[User | None], bool],
        *,
        refusal: str,
        outcome: str | None = None,
    ) -> User:
        """Return `user` if `proven(user)`; otherwise raise
        InvalidCredentialsError with `refusal`, or TooManyAttemptsError while
        throttled.

        Throttled per account and network and per account, keyed on the email
        so the throttle reveals nothing about who has an account. Login,
        deletion and recovery all prove themselves here, so guesses at any of
        them count towards all of them.
        """
        per_network = subject("login", email_key, self._network)
        per_account = subject("login", email_key)
        rules = (
            (LOGIN_PER_ACCOUNT_AND_NETWORK, per_network),
            (LOGIN_PER_ACCOUNT, per_account),
        )
        for rule, key in rules:
            self._refuse_if_throttled(
                rule, key, "Too many failed attempts. Try again in {wait}."
            )

        # Evaluated whether or not there is a user, so the cost is the same.
        if not proven(user) or user is None:
            # Keeps writes: nothing but these records (and perhaps a session
            # refresh) has been written, and they must outlive the error.
            for rule, key in rules:
                bucket = self._limits.record(rule, key)
                if bucket.blocked_until is not None:
                    events.record(
                        "login_throttle_started",
                        rule=rule.scope,
                        subject=key,
                        retry_after_seconds=_seconds(bucket.blocked_until - self._now),
                    )
            failed_for = persisted_id(user) if user is not None else None
            if outcome is None:
                events.record("login_failed", user_id=failed_for, subject=per_account)
            else:
                # Said when it was not a login, so the log does not read as
                # someone failing to sign in.
                events.record(
                    "login_failed",
                    user_id=failed_for,
                    subject=per_account,
                    outcome=outcome,
                )
            raise InvalidCredentialsError(refusal)

        # Proof ends the throttling for this account.
        for rule, key in rules:
            self._limits.clear(rule, key)
        return user

    def _refuse_if_throttled(self, rule: Rule, key: str, message: str) -> None:
        wait = self._limits.wait_remaining(rule, key)
        if wait is None:
            return
        events.record(
            "throttled",
            rule=rule.scope,
            subject=key,
            retry_after_seconds=_seconds(wait),
        )
        raise TooManyAttemptsError(
            message.format(wait=_describe(wait)), retry_after=wait
        )

    def _new_credentials(self, email: str, password: str) -> tuple[str, str]:
        """The normalised email and password hash for a new login, after the
        checks every way of getting one goes through: an email shaped like
        an address, an acceptable password, and an email no one else has."""
        email = normalise_email(email)
        check_password_policy(password, email=email)
        if self._users.find_by_email(email) is not None:
            raise EmailTakenError(
                "An account with that email already exists. Log in instead."
            )
        return email, hash_password(password)

    def _start_session(
        self, user: User, *, recovery_code: str | None = None
    ) -> SignedIn:
        token = new_session_token()
        token_hash = hash_session_token(token)
        user_id = persisted_id(user)
        self._sessions.create(token_hash, user_id, self._now + SESSION_LIFETIME)
        self._users.touch(user_id, self._now)
        return SignedIn(
            user=_current(user, token_hash), token=token, recovery_code=recovery_code
        )


def _current(user: User, token_hash: str) -> CurrentUser:
    return CurrentUser(
        id=persisted_id(user),
        email=user.email,
        is_guest=user.is_guest,
        token_hash=token_hash,
        has_recovery_code=user.recovery_code_hash is not None,
    )


def _seconds(wait: timedelta) -> int:
    return max(1, math.ceil(wait.total_seconds()))


def _describe(wait: timedelta) -> str:
    """'45 seconds', '1 minute', '15 minutes': rounded up, never 'now'."""
    seconds = _seconds(wait)
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _as_utc(moment: datetime) -> datetime:
    """SQLite hands timestamps back without a zone; they were stored as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
