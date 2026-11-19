"""Turning domain objects into API response models."""

from __future__ import annotations

from app.models import (
    Category,
    DayOfWeek,
    GroceryUsual,
    Ingredient,
    Meal,
    MealIngredient,
    WeeklyPlan,
    persisted_id,
)
from app.parsing import ParsedLine
from app.planner import GroceryItem
from app.templates import MealTemplate
from server.schemas import (
    DayAssignment,
    GroceryLine,
    GroceryUsualRead,
    IngredientAmount,
    MealRead,
    ParsedIngredient,
    TemplateIngredientRead,
    TemplateRead,
)


def ingredient_amount(link: MealIngredient, ingredient: Ingredient) -> IngredientAmount:
    return IngredientAmount(
        ingredient_id=persisted_id(ingredient),
        name=ingredient.name,
        qty=link.qty or 0,
        unit=link.unit or "",
    )


def meal_read(
    meal: Meal, ingredients: list[tuple[MealIngredient, Ingredient]]
) -> MealRead:
    return MealRead(
        id=persisted_id(meal),
        name=meal.name,
        servings=meal.servings,
        ingredients=[ingredient_amount(link, ing) for link, ing in ingredients],
    )


def day_assignment(plan: WeeklyPlan) -> DayAssignment:
    return DayAssignment(
        day=DayOfWeek(plan.day_of_week),
        meal_id=plan.meal_id,
        servings=plan.servings,
    )


def grocery_line(item: GroceryItem) -> GroceryLine:
    return GroceryLine(
        key=item.key,
        name=item.name,
        qty=item.qty,
        unit=item.unit,
        display=item.display_qty,
        category=Category(item.category) if item.category else None,
        state=item.state,
        extra_id=item.extra_id,
    )


def grocery_usual(usual: GroceryUsual) -> GroceryUsualRead:
    return GroceryUsualRead(
        id=persisted_id(usual),
        name=usual.name,
        qty=usual.qty,
        unit=usual.unit,
        display=GroceryItem(usual.name, usual.qty, usual.unit).display_qty,
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


def parsed_ingredient(line: ParsedLine) -> ParsedIngredient:
    return ParsedIngredient(
        text=line.text,
        qty=line.qty,
        unit=line.unit,
        name=line.name,
        prep=line.prep,
        catalog_item=line.catalog_item,
        confidence=line.confidence,
        warnings=list(line.warnings),
    )
