"""Domain errors raised by the repositories.

Each carries a message written for the person using the app, so the UI can
surface `str(exc)` directly instead of translating error codes.
"""

from __future__ import annotations


class MealPlannerError(Exception):
    """Base class for every expected, user-facing failure."""


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
