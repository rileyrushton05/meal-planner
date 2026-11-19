"""Weekly plan and grocery list endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.models import DayOfWeek, persisted_id
from app.planner import weekly_shopping
from app.suggest import day_date, suggest_for_empty_days
from server import serializers
from server.deps import ServicesDep
from server.schemas import (
    DayAssignment,
    GroceryLine,
    PlanSuggestions,
    WeekPlanRead,
    WeekPlanWrite,
)

router = APIRouter(prefix="/api", tags=["plan"])


def monday_of(day: date) -> date:
    """Snap any date back to the Monday of its week.

    Done server-side so every client agrees on where a week begins.
    """
    return day - timedelta(days=day.weekday())


@router.get("/plan/{week}", response_model=WeekPlanRead)
def get_plan(week: date, services: ServicesDep) -> WeekPlanRead:
    """The meals assigned to each day of the week containing `week`."""
    week_start = monday_of(week)
    return WeekPlanRead(
        week_start=week_start,
        days=[
            serializers.day_assignment(plan)
            for plan in services.plans.get_week(week_start)
        ],
    )


@router.put("/plan/{week}", response_model=WeekPlanRead)
def set_plan(week: date, payload: WeekPlanWrite, services: ServicesDep) -> WeekPlanRead:
    """Assign several days at once, in a single transaction."""
    week_start = monday_of(week)
    services.plans.set_week(
        week_start,
        {day.day: (day.meal_id, day.servings) for day in payload.days},
    )
    return get_plan(week_start, services)


@router.post("/plan/{week}/copy-previous", response_model=WeekPlanRead)
def copy_previous_week(week: date, services: ServicesDep) -> WeekPlanRead:
    """Carry the previous week's assignments onto this one.

    Days unassigned in the source are skipped rather than clearing the
    target, so copying never destroys work already done here.
    """
    week_start = monday_of(week)
    services.plans.copy_week(week_start - timedelta(days=7), week_start)
    return get_plan(week_start, services)


@router.get("/plan/{week}/suggestions", response_model=PlanSuggestions)
def suggest_meals(
    week: date,
    services: ServicesDep,
    empty: Annotated[list[DayOfWeek], Query(max_length=7)] = [],  # noqa: B006
    planned: Annotated[list[int], Query(max_length=7)] = [],  # noqa: B006
) -> PlanSuggestions:
    """A meal for each `empty` day: the ones not cooked recently, never one
    of the `planned` meals already on this week (app/suggest.py).

    Saves nothing. The page says which days are empty and what is planned,
    rather than the server reading its saved week, because the page may
    hold changes still on their way; it applies the suggestions as one
    change, which it saves and can undo.
    """
    week_start = monday_of(week)
    history = [
        (row.meal_id, day_date(row.week_start_date, DayOfWeek(row.day_of_week)))
        for row in services.plans.list_planned()
        if row.meal_id is not None
    ]
    chosen = suggest_for_empty_days(
        week_start=week_start,
        empty=empty,
        meal_ids=[persisted_id(meal) for meal in services.meals.list_all()],
        planned=history,
        already_this_week=planned,
    )
    return PlanSuggestions(
        week_start=week_start,
        days=[
            DayAssignment(day=day, meal_id=meal_id, servings=None)
            for day, meal_id in chosen.items()
        ],
    )


@router.get("/grocery-list/{week}", response_model=list[GroceryLine])
def grocery_list(week: date, services: ServicesDep) -> list[GroceryLine]:
    """The week's lines alone. Superseded by GET /api/groceries/{week};
    kept so a page loaded before that existed keeps working until reloaded.
    """
    items = weekly_shopping(services.plans, services.groceries, monday_of(week))
    return [serializers.grocery_line(item) for item in items]
