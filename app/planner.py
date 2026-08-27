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
    totals: dict[tuple[str, str], float] = {}

    with db.session() as session:
        plans = session.exec(
            select(WeeklyPlan).where(WeeklyPlan.week_start_date == week_start_date)
        ).all()

        for plan in plans:
            if not plan.meal_id:
                continue

            meal = session.get(Meal, plan.meal_id)
            scale = _serving_scale(plan.servings, meal.servings if meal else None)

            links = session.exec(
                select(MealIngredient).where(MealIngredient.meal_id == plan.meal_id)
            ).all()

            for link in links:
                ingredient = session.get(Ingredient, link.ingredient_id)
                if ingredient is None:
                    continue
                qty, unit = units.normalize((link.qty or 0) * scale, link.unit)
                key = (ingredient.name, unit)
                totals[key] = totals.get(key, 0.0) + qty

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
