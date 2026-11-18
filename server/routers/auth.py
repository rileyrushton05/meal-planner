"""Signing in and out: guest sessions, signup, login, logout, and who am I.

The rules live in app/auth.py. These handlers only move the session token
between the cookie and AuthService.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Response, status

from app.auth import CurrentUser, SignedIn
from server.deps import (
    SESSION_COOKIE,
    AuthDep,
    CurrentUserDep,
    OptionalUserDep,
)
from server.schemas import Account, Credentials, GuestStart, Recovery, SignedUp

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: How long the browser keeps the cookie: 400 days, the most Chrome allows.
#: The server decides whether the session is still valid (30 days without
#: a visit); a cookie that outlives its session is just a dead token. A
#: shorter cookie would log out someone who visits every day, because it is
#: only set at sign-in, not refreshed on every visit.
_COOKIE_MAX_AGE = int(timedelta(days=400).total_seconds())


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_COOKIE_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    # The attributes must match, or the browser treats it as another cookie;
    # a __Host- cookie cannot even be cleared without Secure.
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
    )


def _account(user: CurrentUser) -> Account:
    return Account(
        email=user.email,
        is_guest=user.is_guest,
        has_recovery_code=user.has_recovery_code,
    )


def _signed_up(response: Response, result: SignedIn) -> SignedUp:
    """Signed in, with the new recovery code to show the person once."""
    assert result.recovery_code is not None, "a recovery code was issued"
    _set_session_cookie(response, result.token)
    return SignedUp(
        **_account(result.user).model_dump(), recovery_code=result.recovery_code
    )


def _signed_in(response: Response, result: SignedIn) -> Account:
    _set_session_cookie(response, result.token)
    return _account(result.user)


@router.post(
    "/guest",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": Account, "description": "Already signed in."}},
)
def start_guest(
    response: Response,
    auth: AuthDep,
    current: OptionalUserDep,
    payload: Annotated[GuestStart | None, Body()] = None,
) -> Account:
    """Start a guest session: a real account with no email or password.

    The app calls this when a request comes back 401, so a first visit
    lands straight in a working planner, with sample meals if it asks for
    them. A caller who is already signed in gets their own account back
    (200) rather than a second one.
    """
    if current is not None:
        response.status_code = status.HTTP_200_OK
        return _account(current)
    sample_week = payload.sample_week if payload is not None else None
    return _signed_in(response, auth.start_guest(sample_week))


@router.post("/signup")
def sign_up(
    payload: Credentials, response: Response, auth: AuthDep, current: OptionalUserDep
) -> SignedUp:
    """Create an account. A guest becomes the account, keeping their data.

    The response carries the account's recovery code, shown once: the only
    way back in if the password is forgotten.
    """
    return _signed_up(response, auth.sign_up(current, payload.email, payload.password))


@router.post("/recover")
def recover(
    payload: Recovery, response: Response, auth: AuthDep, current: OptionalUserDep
) -> SignedUp:
    """Set a new password with the email and recovery code, and sign in.

    Ends every other session of the account, and replaces the recovery code
    (each works once): the response carries the new one. The refusal is the
    same whether the email or the code is wrong, 401 invalid-credentials,
    throttled with login.
    """
    return _signed_up(
        response,
        auth.recover(
            current, payload.email, payload.recovery_code, payload.new_password
        ),
    )


@router.post("/login")
def log_in(
    payload: Credentials, response: Response, auth: AuthDep, current: OptionalUserDep
) -> Account:
    """Sign in with an email and password. Always issues a new session."""
    return _signed_in(response, auth.log_in(current, payload.email, payload.password))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(auth: AuthDep, current: OptionalUserDep) -> Response:
    """End this session. Succeeds even if it had already ended."""
    if current is not None:
        auth.log_out(current)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/me")
def who_am_i(current: CurrentUserDep) -> Account:
    """The signed-in account, or 401 not-signed-in."""
    return _account(current)
