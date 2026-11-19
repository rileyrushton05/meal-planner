"""Turning a week's planned meals into a consolidated grocery list."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from app import units
from app.models import Category, CheckState, grocery_key, persisted_id
from app.repositories import GroceryRepository, WeeklyPlanRepository


@dataclass(frozen=True, slots=True)
class GroceryItem:
    """How much of one ingredient to buy.

    `qty` stays numeric rather than pre-formatted so callers can sort, total
    or price it; `display_qty` handles presentation.
    """

    name: str
    #: None only for an extra added with no amount ("milk").
    qty: float | None
    #: Empty for count-based items ("2 onions").
    unit: str
    #: The aisle (a `Category` value), or None when the catalogue does not
    #: know the ingredient.
    category: str | None = None
    #: Set for something added to the week's list by hand, not by a meal.
    extra_id: int | None = None
    #: Ticked off, or already at home; None while still to get.
    state: CheckState | None = None

    @property
    def key(self) -> str:
        """What a tick is stored against (`models.grocery_key`)."""
        return grocery_key(self.name, self.unit, extra=self.extra_id is not None)

    @property
    def display_qty(self) -> str:
        """The amount as a shopper reads it, e.g. "1.5 kg" rather than "1500 g"."""
        if self.qty is None:
            return ""
        return units.format_amount(*units.humanize(self.qty, self.unit))

    def __str__(self) -> str:
        return f"{self.name}: {self.display_qty}"


def generate_weekly_grocery_list(
    plans: WeeklyPlanRepository,
    week_start_date: date,
    aisle_order: Sequence[Category] = tuple(Category),
) -> list[GroceryItem]:
    """Total everything needed for one week, in aisle order, then by
    ingredient and unit.

    Quantities scale when a day's planned servings differ from the recipe,
    and convert to a common base unit where that is unambiguous. Units that
    cannot be converted between each other stay as separate lines. Counted
    things are rounded up to whole ones once totalled, since that is how
    they are bought: half a lettuce on Monday and half on Friday is one.

    Takes the repository rather than a Database so the read joins whatever
    transaction the caller already has open, instead of starting a second.
    """
    totals: dict[tuple[str, str], float] = {}
    aisles: dict[str, str | None] = {}

    for name, qty, unit, planned, base, category in plans.ingredient_rows_for_week(
        week_start_date
    ):
        scale = planned / base if planned and base else 1.0
        scaled_qty, base_unit = units.normalize((qty or 0) * scale, unit)
        key = (name, base_unit)
        totals[key] = totals.get(key, 0.0) + scaled_qty
        aisles[name] = category

    items = [
        GroceryItem(
            name=name,
            qty=units.to_buy(qty, unit),
            unit=unit,
            category=aisles[name],
        )
        for (name, unit), qty in totals.items()
    ]
    return in_aisle_order(items, aisle_order)


def in_aisle_order(
    items: Sequence[GroceryItem], aisle_order: Sequence[Category]
) -> list[GroceryItem]:
    """Aisle by aisle in the person's order, the unknown last; by name and
    unit within an aisle."""
    position = {category.value: index for index, category in enumerate(aisle_order)}
    return sorted(
        items,
        key=lambda item: (
            position.get(item.category or "", len(position)),
            item.name.casefold(),
            item.unit,
        ),
    )


def weekly_shopping(
    plans: WeeklyPlanRepository, groceries: GroceryRepository, week_start_date: date
) -> list[GroceryItem]:
    """The week's whole list as the shopper sees it: the meals' lines, the
    extras added by hand, each marked as ticked off or at home, in the
    person's aisle order."""
    order = groceries.aisle_order()
    extras = [
        GroceryItem(
            name=extra.name,
            qty=extra.qty,
            unit=extra.unit,
            category=category,
            extra_id=persisted_id(extra),
        )
        for extra, category in groceries.extras(week_start_date)
    ]
    checks = groceries.checks(week_start_date)
    return [
        replace(item, state=checks.get(item.key))
        for item in in_aisle_order(
            [*generate_weekly_grocery_list(plans, week_start_date), *extras], order
        )
    ]
