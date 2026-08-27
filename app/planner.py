"""Turning a week's planned meals into a consolidated grocery list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import select

from app import units
from app.db import Database
from app.models import Ingredient, Meal, MealIngredient, WeeklyPlan


@dataclass(frozen=True, slots=True)
class GroceryItem:
    """One line of a grocery list: how much of one ingredient to buy.

    Quantity stays numeric rather than pre-formatted, so callers can sort,
    total or price it. Use :meth:`display_qty` for presentation.
    """

    name: str
    qty: float
    #: Empty for count-based items ("2 onions"), which have no unit.
    unit: str

    @property
    def display_qty(self) -> str:
        """The amount as shown to a shopper, e.g. "400 g" or "2"."""
        return f"{units.format_qty(self.qty)} {self.unit}".strip()

    def __str__(self) -> str:
        return f"{self.name}: {self.display_qty}"


def generate_weekly_grocery_list(
    db: Database, week_start_date: date
) -> list[GroceryItem]:
    """Total up everything needed for the meals planned in one week.

    Quantities are scaled when a day's planned servings differ from the
    meal's base recipe size, converted to a common base unit where that is
    unambiguous (see :mod:`app.units`), then summed per ingredient.

    An ingredient recorded in units that cannot be converted between each
    other (say millilitres in one meal and cups in another) yields one line
    per unit, since combining them would require guessing.

    Returns:
        Lines sorted by ingredient name, then by unit.
    """
    # One query, joined across all four tables. Fetching the meal and then
    # each ingredient row by row instead cost 48 statements for a full week,
    # which is unnoticeable on a local SQLite file and roughly two and a half
    # seconds against a database on the other end of a network.
    statement = (
        select(
            Ingredient.name,
            MealIngredient.qty,
            MealIngredient.unit,
            WeeklyPlan.servings,
            Meal.servings,
        )
        .select_from(WeeklyPlan)
        .join(Meal, Meal.id == WeeklyPlan.meal_id)
        .join(MealIngredient, MealIngredient.meal_id == Meal.id)
        .join(Ingredient, Ingredient.id == MealIngredient.ingredient_id)
        .where(WeeklyPlan.week_start_date == week_start_date)
    )

    totals: dict[tuple[str, str], float] = {}

    with db.session() as session:
        for name, qty, unit, planned_servings, base_servings in session.exec(statement):
            scale = _serving_scale(planned_servings, base_servings)
            scaled_qty, base_unit = units.normalize((qty or 0) * scale, unit)
            key = (name, base_unit)
            totals[key] = totals.get(key, 0.0) + scaled_qty

    return [
        GroceryItem(name=name, qty=qty, unit=unit)
        for (name, unit), qty in sorted(totals.items())
    ]


def _serving_scale(planned: int | None, base: int | None) -> float:
    """How much to multiply a recipe's quantities by for a given day.

    Returns 1.0 when either figure is missing or zero, meaning "use the
    recipe as written".
    """
    if planned and base:
        return planned / base
    return 1.0


def format_grocery_list(items: list[GroceryItem]) -> str:
    """Render a grocery list as plain text, for copying or downloading."""
    return "\n".join(f"- {item}" for item in items)
