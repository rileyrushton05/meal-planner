"""A week's grocery list as the shopper uses it: ticks, extras, usuals and
the aisle order.

The lines are derived from the plan (app/planner.py); what is stored is only
what a person did to them, so the same list, ticked the same way, shows on
every device they sign in on.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response, status

from app.exceptions import NothingToAddError
from app.models import Category
from app.parsing import ParsedLine, parse_line
from app.planner import weekly_shopping
from server import serializers
from server.deps import Services, ServicesDep
from server.routers.plans import monday_of
from server.schemas import (
    AisleOrder,
    GroceryCheckWrite,
    GroceryItemText,
    GroceryList,
    GroceryUsualRead,
)

router = APIRouter(prefix="/api", tags=["groceries"])


def _list(services: Services, week_start: date) -> GroceryList:
    return GroceryList(
        week_start=week_start,
        lines=[
            serializers.grocery_line(item)
            for item in weekly_shopping(services.plans, services.groceries, week_start)
        ],
        usuals=_usuals(services),
        aisle_order=services.groceries.aisle_order(),
    )


def _usuals(services: Services) -> list[GroceryUsualRead]:
    return [serializers.grocery_usual(u) for u in services.groceries.usuals()]


def _item(text: str) -> ParsedLine:
    """Read "2 L milk" as the recipe reader would; it must name something."""
    parsed = parse_line(text)
    if not parsed.name.strip():
        raise NothingToAddError("Say what to add, like 2 L milk.")
    return parsed


@router.get("/groceries/{week}", response_model=GroceryList)
def get_groceries(week: date, services: ServicesDep) -> GroceryList:
    """The week's list: the meals' lines and the extras, each marked as
    still to get, in the basket or at home, in the person's aisle order."""
    return _list(services, monday_of(week))


@router.put("/groceries/{week}/checks", status_code=status.HTTP_204_NO_CONTENT)
def set_check(
    week: date, payload: GroceryCheckWrite, services: ServicesDep
) -> Response:
    """Tick a line off, mark it as at home, or put it back to get.

    Answers with nothing rather than the list: ticking happens fast, in the
    shop, and the page already shows the tick. A key no line has is stored
    harmlessly, since lines come and go with the plan.
    """
    services.groceries.set_check(monday_of(week), payload.key, payload.state)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/groceries/{week}/basket", response_model=GroceryList)
def empty_basket(week: date, services: ServicesDep) -> GroceryList:
    """Start the shop again: untick everything, keeping what is at home."""
    week_start = monday_of(week)
    services.groceries.empty_basket(week_start)
    return _list(services, week_start)


@router.post("/groceries/{week}/extras", response_model=GroceryList)
def add_extra(
    week: date, payload: GroceryItemText, services: ServicesDep
) -> GroceryList:
    """Add something no meal needs. Already on the list: its amount changes."""
    week_start = monday_of(week)
    item = _item(payload.text)
    services.groceries.add_extra(week_start, item.name, item.qty, item.unit)
    return _list(services, week_start)


@router.delete("/groceries/{week}/extras/{extra_id}", response_model=GroceryList)
def remove_extra(week: date, extra_id: int, services: ServicesDep) -> GroceryList:
    week_start = monday_of(week)
    services.groceries.remove_extra(week_start, extra_id)
    return _list(services, week_start)


@router.post("/groceries/{week}/extras/{extra_id}/keep", response_model=GroceryList)
def keep_as_usual(week: date, extra_id: int, services: ServicesDep) -> GroceryList:
    """Keep an extra as a usual, at its amount, for adding to later weeks."""
    week_start = monday_of(week)
    extra = services.groceries.extra(week_start, extra_id)
    services.groceries.add_usual(extra.name, extra.qty, extra.unit)
    return _list(services, week_start)


@router.post("/groceries/{week}/add-usuals", response_model=GroceryList)
def add_usuals(week: date, services: ServicesDep) -> GroceryList:
    """Every usual onto the week's list in one go; ones already there by
    name keep the amount they have."""
    week_start = monday_of(week)
    services.groceries.add_usuals(week_start)
    return _list(services, week_start)


@router.post("/usuals", response_model=list[GroceryUsualRead])
def add_usual(
    payload: GroceryItemText, services: ServicesDep
) -> list[GroceryUsualRead]:
    item = _item(payload.text)
    services.groceries.add_usual(item.name, item.qty, item.unit)
    return _usuals(services)


@router.delete("/usuals/{usual_id}", response_model=list[GroceryUsualRead])
def remove_usual(usual_id: int, services: ServicesDep) -> list[GroceryUsualRead]:
    services.groceries.remove_usual(usual_id)
    return _usuals(services)


@router.put("/aisle-order", response_model=list[Category])
def set_aisle_order(payload: AisleOrder, services: ServicesDep) -> list[Category]:
    """The order of the aisles in this person's shop, for every week."""
    services.groceries.set_aisle_order(payload.aisle_order)
    return services.groceries.aisle_order()
