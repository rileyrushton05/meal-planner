"""Reading ingredient lines before they are saved."""

from __future__ import annotations

from fastapi import APIRouter

from app.parsing import parse_lines
from server import serializers
from server.deps import CurrentUserDep
from server.schemas import IngredientText, ParsedIngredients

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


@router.post("/parse", response_model=ParsedIngredients)
def parse_ingredients(
    payload: IngredientText, _user: CurrentUserDep
) -> ParsedIngredients:
    """Read pasted lines as amounts, units and names, for a preview. Saves
    nothing: the client sends the checked list to
    `PUT /api/meals/{id}/ingredients`.

    Needs a session like every data route, though it reads no data, so the
    parser is not open to anyone on the internet. The body's size and line
    count are bounded (IngredientText), so the work is too.
    """
    return ParsedIngredients(
        lines=[
            serializers.parsed_ingredient(line) for line in parse_lines(payload.text)
        ]
    )
