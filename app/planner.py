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
        return f"{units.format_qty(self.qty)} {self.unit}".strip()

    def __str__(self) -> str:
        return f"{self.name}: {self.display_qty}"


def generate_weekly_grocery_list(
    db: Database, week_start_date: date
) -> list[GroceryItem]:
    """Total everything needed for one week, sorted by ingredient then unit.

    Quantities scale when a day's planned servings differ from the recipe,
    and convert to a common base unit where that is unambiguous. Units that
    cannot be converted between each other stay as separate lines.
    """
    # One join rather than a query per meal and per ingredient, which cost 48
    # statements for a full week - free on SQLite, ~2.4s across a network.
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
        for name, qty, unit, planned, base in session.exec(statement):
            scale = planned / base if planned and base else 1.0
            scaled_qty, base_unit = units.normalize((qty or 0) * scale, unit)
            key = (name, base_unit)
            totals[key] = totals.get(key, 0.0) + scaled_qty

    return [
        GroceryItem(name=name, qty=qty, unit=unit)
        for (name, unit), qty in sorted(totals.items())
    ]
