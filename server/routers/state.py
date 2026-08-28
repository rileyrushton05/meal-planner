"""The bootstrap endpoint the frontend loads a week from."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from server import serializers
from server.deps import Services, get_services
from server.routers.plans import monday_of
from server.schemas import AppState, TemplateRead
from app.templates import MEAL_TEMPLATES

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/state", response_model=AppState)
def get_state(
    week: date | None = None, services: Services = Depends(get_services)
) -> AppState:
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

    return AppState(
        week_start=week_start,
        meals=meals,
        ingredient_names=sorted(
            {ingredient.name for ingredient in services.ingredients.list_all()}
        ),
        plan=[
            serializers.day_assignment(plan)
            for plan in services.plans.get_week(week_start)
        ],
        templates=[serializers.template_read(t) for t in MEAL_TEMPLATES],
    )


@router.get("/templates", response_model=list[TemplateRead])
def list_templates() -> list[TemplateRead]:
    """The built-in starter meals. Static, so no database access."""
    return [serializers.template_read(t) for t in MEAL_TEMPLATES]
