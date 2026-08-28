"""Turning domain objects into API response models."""

from __future__ import annotations

from app.models import Ingredient, Meal, MealIngredient, WeeklyPlan
from app.planner import GroceryItem
from app.templates import MealTemplate
from api.schemas import (
    DayAssignment,
    GroceryLine,
    IngredientAmount,
    MealRead,
    TemplateIngredientRead,
    TemplateRead,
)


def ingredient_amount(link: MealIngredient, ingredient: Ingredient) -> IngredientAmount:
    return IngredientAmount(
        ingredient_id=ingredient.id,
        name=ingredient.name,
        qty=link.qty or 0,
        unit=link.unit or "",
    )


def meal_read(
    meal: Meal, ingredients: list[tuple[MealIngredient, Ingredient]]
) -> MealRead:
    return MealRead(
        id=meal.id,
        name=meal.name,
        servings=meal.servings,
        ingredients=[ingredient_amount(link, ing) for link, ing in ingredients],
    )


def day_assignment(plan: WeeklyPlan) -> DayAssignment:
    return DayAssignment(
        day=plan.day_of_week, meal_id=plan.meal_id, servings=plan.servings
    )


def grocery_line(item: GroceryItem) -> GroceryLine:
    return GroceryLine(
        name=item.name, qty=item.qty, unit=item.unit, display=item.display_qty
    )


def template_read(template: MealTemplate) -> TemplateRead:
    return TemplateRead(
        name=template.name,
        servings=template.servings,
        ingredients=[
            TemplateIngredientRead(name=item.name, qty=item.qty, unit=item.unit)
            for item in template.ingredients
        ],
    )
