"""Weekly plan and grocery list endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends

from api import serializers
from api.deps import Services, get_services
from api.schemas import GroceryLine, WeekPlanRead, WeekPlanWrite
from app.planner import generate_weekly_grocery_list

router = APIRouter(prefix="/api", tags=["plan"])


def monday_of(day: date) -> date:
    """Snap any date back to the Monday of its week.

    Done server-side so every client agrees on where a week begins.
    """
    return day - timedelta(days=day.weekday())


@router.get("/plan/{week}", response_model=WeekPlanRead)
def get_plan(week: date, services: Services = Depends(get_services)) -> WeekPlanRead:
    """The meals assigned to each day of the week containing `week`."""
    week_start = monday_of(week)
    return WeekPlanRead(
        week_start=week_start,
        days=[serializers.day_assignment(p) for p in services.plans.get_week(week_start)],
    )


@router.put("/plan/{week}", response_model=WeekPlanRead)
def set_plan(
    week: date, payload: WeekPlanWrite, services: Services = Depends(get_services)
) -> WeekPlanRead:
    """Assign several days at once, in a single transaction."""
    week_start = monday_of(week)
    services.plans.set_week(
        week_start,
        {day.day: (day.meal_id, day.servings) for day in payload.days},
    )
    return get_plan(week_start, services)


@router.post("/plan/{week}/copy-previous", response_model=WeekPlanRead)
def copy_previous_week(
    week: date, services: Services = Depends(get_services)
) -> WeekPlanRead:
    """Carry the previous week's assignments onto this one.

    Days unassigned in the source are skipped rather than clearing the
    target, so copying never destroys work already done here.
    """
    week_start = monday_of(week)
    services.plans.copy_week(week_start - timedelta(days=7), week_start)
    return get_plan(week_start, services)


@router.get("/grocery-list/{week}", response_model=list[GroceryLine])
def grocery_list(
    week: date, services: Services = Depends(get_services)
) -> list[GroceryLine]:
    """Consolidated shopping list for the week containing `week`."""
    items = generate_weekly_grocery_list(services.db, monday_of(week))
    return [serializers.grocery_line(item) for item in items]
