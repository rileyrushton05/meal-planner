"""The bootstrap endpoint the frontend loads a week from."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app.suggestions import ingredient_suggestions
from app.templates import MEAL_TEMPLATES
from server import serializers
from server.deps import ServicesDep
from server.routers.plans import monday_of
from server.schemas import AppState, IngredientSuggestion

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/state", response_model=AppState)
def get_state(services: ServicesDep, week: date | None = None) -> AppState:
    """Everything needed to render the app for one week, in one response.

    Deliberately one endpoint rather than four. The Streamlit version issued
    a separate query per section on every interaction, which cost nothing
    against a local SQLite file and roughly a second against a database
    across a network. Clients fetch this once and hold it.
    """
    week_start = monday_of(week or date.today())

    meals = [
        serializers.meal_read(meal, ingredients)
        for meal, ingredients in services.meals.list_all_with_ingredients()
    ]

    suggestions = ingredient_suggestions(
        (ingredient.name for ingredient in services.ingredients.list_all()),
        ((line.name, line.unit) for meal in meals for line in meal.ingredients),
    )

    return AppState(
        week_start=week_start,
        meals=meals,
        ingredient_suggestions=[
            IngredientSuggestion(name=s.name, unit=s.unit) for s in suggestions
        ],
        plan=[
            serializers.day_assignment(plan)
            for plan in services.plans.get_week(week_start)
        ],
        templates=[serializers.template_read(t) for t in MEAL_TEMPLATES],
    )
