"""Shared dependencies: the request's transaction, who is asking, and the
repositories over both."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.auth import AuthService, CurrentUser
from app.db import Database, act_as, load_env_file
from app.exceptions import NotSignedInError
from app.repositories import (
    GroceryRepository,
    IngredientRepository,
    MealRepository,
    WeeklyPlanRepository,
)

#: The session cookie. The `__Host-` prefix makes the browser refuse it
#: unless it is Secure, has Path=/ and no Domain, so nothing on another
#: subdomain can set or overwrite it.
SESSION_COOKIE = "__Host-session"


@dataclass(frozen=True, slots=True)
class Services:
    """Everything a route handler needs to read or change data, already
    scoped to the signed-in user."""

    meals: MealRepository
    ingredients: IngredientRepository
    plans: WeeklyPlanRepository
    groceries: GroceryRepository


@lru_cache(maxsize=1)
def get_database() -> Database:
    """The process-wide Database. One engine, so the pool is actually reused.

    Establishing a connection costs several network round trips - far more
    than a query - so rebuilding the pool per request would dominate every
    response time.
    """
    load_env_file()
    return Database()


def get_transaction() -> Generator[Session]:
    """One transaction per request, shared by everything the request does.

    Everything a request does commits together or not at all: a route that
    raises, a domain error included, rolls back whatever it had written. One
    BEGIN/COMMIT per request rather than per repository saved about 1.5 s of
    a 3.4 s week change against a database a network away.
    """
    with get_database().transaction() as session:
        yield session


#: `scope="function"` makes the transaction commit when the route returns,
#: before the response is sent. FastAPI's default scope finishes yield
#: dependencies after the response has gone out, so a commit that failed
#: there (a dropped connection, a constraint checked at commit) would
#: already have told the client 200 for a write that never happened.
#: tests/test_transactions.py proves the difference.
TransactionDep = Annotated[Session, Depends(get_transaction, scope="function")]


def client_address(request: Request) -> str:
    """The caller's IP address, for throttling.

    On Vercel, the last entry of `x-vercel-forwarded-for`, the header the
    platform sets. Never `x-forwarded-for` or `x-real-ip`, which a client can
    write itself: trusting them would let anyone dodge a limit by sending a
    different made-up address each time. Last rather than first, because a
    proxy appends the address it saw, so anything before that came from the
    client. Elsewhere (local development, tests) no proxy is trusted at all.
    """
    if os.getenv("VERCEL"):
        forwarded = request.headers.get("x-vercel-forwarded-for", "")
        last = forwarded.rsplit(",", 1)[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def get_auth(request: Request, session: TransactionDep) -> AuthService:
    return AuthService(session, now=datetime.now(UTC), address=client_address(request))


AuthDep = Annotated[AuthService, Depends(get_auth)]


def get_current_user(request: Request, auth: AuthDep) -> CurrentUser:
    """The signed-in user, or 401 not-signed-in."""
    return auth.authenticate(request.cookies.get(SESSION_COOKIE))


def get_optional_user(request: Request, auth: AuthDep) -> CurrentUser | None:
    """The signed-in user, or None: for the auth routes, which work either
    way."""
    try:
        return get_current_user(request, auth)
    except NotSignedInError:
        return None


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


def get_services(session: TransactionDep, user: CurrentUserDep) -> Services:
    """The repositories for this request, bound to its user. Requiring this
    is what makes a route need a session: there is no way to get
    repositories without one.

    Two layers, set from the same user: the repositories filter every query
    by them, and `act_as` tells Postgres, whose row-level security filters
    again, so a query that forgot its filter still sees only their rows.
    """
    act_as(session, user.id)
    return Services(
        meals=MealRepository(session, user_id=user.id),
        ingredients=IngredientRepository(session, user_id=user.id),
        plans=WeeklyPlanRepository(session, user_id=user.id),
        groceries=GroceryRepository(session, user_id=user.id),
    )


#: What route handlers annotate their `services` parameter with.
#: Annotated rather than a `Depends()` default, which FastAPI still accepts
#: but which evaluates a call at import time and reads as a mutable default.
ServicesDep = Annotated[Services, Depends(get_services)]


def reset_services_cache() -> None:
    """Drop the cached engine. Used by tests between cases."""
    get_database.cache_clear()
