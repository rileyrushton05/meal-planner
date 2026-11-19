"""Importing a recipe from a link: fetch the page (app/fetch.py), find its
Recipe data (app/recipes.py), read each ingredient line (app/parsing.py).

Nothing is saved: the result is a preview, which the person checks and
saves as a new meal. Each attempt counts against a per-user hourly limit,
successful or not, before anything is fetched.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from app import events
from app.exceptions import RecipeImportError, TooManyAttemptsError
from app.fetch import FetchRefused, Page, fetch_page
from app.parsing import ParsedLine, parse_line
from app.ratelimit import (
    IMPORTS_PER_USER,
    RateLimiter,
    describe_wait,
    subject,
    wait_seconds,
)
from app.recipes import find_recipe

#: One origin the end-to-end tests serve their fixture recipe from, exempt
#: from the public-address check. Ignored on Vercel, so it cannot open a
#: hole in production even if it were set there.
UNCHECKED_ORIGIN_ENV_VAR = "MEAL_PLANNER_IMPORT_UNCHECKED_ORIGIN"


@dataclass(frozen=True, slots=True)
class ImportedRecipe:
    name: str
    servings: int | None
    #: Where the page was found, after redirects.
    url: str
    lines: list[ParsedLine]


def import_recipe(
    session: Session,
    *,
    user_id: int,
    url: str,
    now: datetime,
    fetch: Callable[..., Page] | None = None,
) -> ImportedRecipe:
    """Raises TooManyAttemptsError over the limit, and RecipeImportError,
    with a sentence for the person, for a page that cannot be fetched or
    has no recipe in it."""
    limits = RateLimiter(session, now=now)
    key = subject("user", str(user_id))
    wait = limits.wait_remaining(IMPORTS_PER_USER, key)
    if wait is not None:
        events.record(
            "throttled",
            rule=IMPORTS_PER_USER.scope,
            subject=key,
            retry_after_seconds=wait_seconds(wait),
        )
        raise TooManyAttemptsError(
            "That's a lot of recipes imported in the last hour. "
            f"Try again in {describe_wait(wait)}, or paste the ingredients instead.",
            retry_after=wait,
        )
    limits.record(IMPORTS_PER_USER, key)

    try:
        page = (fetch or fetch_page)(url, unchecked_origin=unchecked_origin())
    except FetchRefused as refused:
        raise RecipeImportError(str(refused)) from None

    recipe = find_recipe(page.html)
    if recipe is None:
        raise RecipeImportError(
            "No recipe found on that page. Copy its ingredients and paste them "
            "into a meal instead."
        )
    return ImportedRecipe(
        name=recipe.name,
        servings=recipe.servings,
        url=page.url,
        lines=[parse_line(line) for line in recipe.lines],
    )


def unchecked_origin() -> str | None:
    if os.getenv("VERCEL"):
        return None
    return os.getenv(UNCHECKED_ORIGIN_ENV_VAR) or None
