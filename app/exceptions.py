"""Domain errors raised by the repositories.

Each carries a message written for the person using the app, so the UI can
surface `str(exc)` directly instead of translating error codes.
"""

from __future__ import annotations

import math
from datetime import timedelta


class MealPlannerError(Exception):
    """Base class for every expected, user-facing failure."""


class KeepsWrites(Exception):
    """Marks an error whose request should still commit what it wrote.

    Normally an error rolls the request's transaction back. A failed login
    is an error, and the attempt it records must outlive it, or throttling
    would count nothing: the record would roll back with the request. So
    the few errors raised after recording an attempt carry this marker,
    and `Database.transaction()` commits before letting them through.

    Only safe where nothing but the record has been written by the time the
    error is raised. Each use says so where it is raised.
    """


class DuplicateNameError(MealPlannerError):
    """A meal with that name (ignoring case) already exists."""


class MealNotFoundError(MealPlannerError):
    """The requested meal id doesn't exist."""


class UnitMismatchError(MealPlannerError):
    """An ingredient is already on the meal measured in a different unit."""


class IngredientNotOnMealError(MealPlannerError):
    """The meal exists, but that ingredient is not attached to it."""


class InvalidDayError(MealPlannerError):
    """A day was given that is not one of the seven weekdays."""


class WeakPasswordError(MealPlannerError):
    """A password chosen at signup is too short, too long or too common."""


# --- Accounts ----------------------------------------------------------------


class NotSignedInError(MealPlannerError):
    """No session cookie, or one for a session that has ended."""


class InvalidCredentialsError(KeepsWrites, MealPlannerError):
    """Login failed. Deliberately does not say whether the email exists."""


class InvalidEmailError(MealPlannerError):
    """A signup email that is not shaped like an address."""


class EmailTakenError(KeepsWrites, MealPlannerError):
    """Signup with an email that already has an account."""


class AlreadySignedUpError(MealPlannerError):
    """Signup while signed in to an account (rather than a guest)."""


class NoLoginError(MealPlannerError):
    """Something only an account with a login can do (a recovery code),
    asked by a guest. Not "not signed in": the guest is signed in, and the
    client starts a new guest session on that answer."""


class CrossSiteRequestError(MealPlannerError):
    """A state-changing request sent from another website."""


class TooManyAttemptsError(MealPlannerError):
    """Throttled: too many attempts recently from this account or network."""

    def __init__(self, message: str, *, retry_after: timedelta) -> None:
        self.retry_after_seconds = max(1, math.ceil(retry_after.total_seconds()))
        super().__init__(message)
