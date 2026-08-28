"""Turning a week's planned meals into a consolidated grocery list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app import units
from app.repositories import WeeklyPlanRepository


@dataclass(frozen=True, slots=True)
class GroceryItem:
    """How much of one ingredient to buy.

    `qty` stays numeric rather than pre-formatted so callers can sort, total
    or price it; `display_qty` handles presentation.
    """

    name: str
    qty: float
    #: Empty for count-based items ("2 onions").
    unit: str

    @property
    def display_qty(self) -> str:
        """The amount as a shopper reads it, e.g. "1.5 kg" rather than "1500 g"."""
        qty, unit = units.humanize(self.qty, self.unit)
        return f"{units.format_qty(qty)} {unit}".strip()

    def __str__(self) -> str:
        return f"{self.name}: {self.display_qty}"


def generate_weekly_grocery_list(
    plans: WeeklyPlanRepository, week_start_date: date
) -> list[GroceryItem]:
    """Total everything needed for one week, sorted by ingredient then unit.

    Quantities scale when a day's planned servings differ from the recipe,
    and convert to a common base unit where that is unambiguous. Units that
    cannot be converted between each other stay as separate lines.

    Takes the repository rather than a Database so the read joins whatever
    transaction the caller already has open, instead of starting a second.
    """
    totals: dict[tuple[str, str], float] = {}

    for name, qty, unit, planned, base in plans.ingredient_rows_for_week(
        week_start_date
    ):
        scale = planned / base if planned and base else 1.0
        scaled_qty, base_unit = units.normalize((qty or 0) * scale, unit)
        key = (name, base_unit)
        totals[key] = totals.get(key, 0.0) + scaled_qty

    return [
        GroceryItem(name=name, qty=qty, unit=unit)
        for (name, unit), qty in sorted(totals.items())
    ]
