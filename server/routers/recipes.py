"""Importing a recipe from a link."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from server import serializers
from server.deps import CurrentUserDep, TransactionDep
from server.schemas import ImportedRecipe, RecipeLink

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.post("/import", response_model=ImportedRecipe)
def import_recipe(
    payload: RecipeLink, user: CurrentUserDep, session: TransactionDep
) -> ImportedRecipe:
    """Read the recipe on a web page, for a preview. Saves nothing: the
    checked recipe is created with `POST /api/meals`.

    The server fetches the page, so the URL is held to app/fetch.py's
    rules (public addresses only, checked after every redirect; 5 seconds;
    2 MB; HTML), and each user may import 20 an hour. A page that cannot be
    read is 422 recipe-import, with a sentence saying why.
    """
    # Loaded on first use: fetching pages brings in httpx, which no other
    # request needs, so a cold start does not pay for it.
    from app.importing import import_recipe as read_recipe_at

    recipe = read_recipe_at(
        session, user_id=user.id, url=payload.url, now=datetime.now(UTC)
    )
    return ImportedRecipe(
        name=recipe.name,
        servings=recipe.servings,
        url=recipe.url,
        lines=[serializers.parsed_ingredient(line) for line in recipe.lines],
    )
