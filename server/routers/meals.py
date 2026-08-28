"""Meal and meal-ingredient endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from server import serializers
from server.deps import Services, get_services
from server.schemas import IngredientAdd, IngredientUpdate, MealCreate, MealRead, MealUpdate
from app.templates import MEAL_TEMPLATES

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[MealRead])
def list_meals(services: Services = Depends(get_services)) -> list[MealRead]:
    """Every meal, each with its ingredients."""
    return [
        serializers.meal_read(meal, ingredients)
        for meal, ingredients in services.meals.list_all_with_ingredients()
    ]


@router.post("", response_model=MealRead, status_code=status.HTTP_201_CREATED)
def create_meal(
    payload: MealCreate, services: Services = Depends(get_services)
) -> MealRead:
    """Create a meal. Duplicate names are rejected with 409."""
    meal = services.meals.add(payload.name, servings=payload.servings)
    return serializers.meal_read(meal, [])


@router.post(
    "/from-template/{template_name}",
    response_model=MealRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_from_template(
    template_name: str, services: Services = Depends(get_services)
) -> MealRead:
    """Create a meal and its ingredients from a built-in template."""
    template = next((t for t in MEAL_TEMPLATES if t.name == template_name), None)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No template named '{template_name}'.",
        )

    meal = services.meals.add_from_template(template)
    return serializers.meal_read(meal, services.meals.list_ingredients(meal.id))


@router.patch("/{meal_id}", response_model=MealRead)
def update_meal(
    meal_id: int, payload: MealUpdate, services: Services = Depends(get_services)
) -> MealRead:
    """Rename a meal or change its base serving size."""
    services.meals.update(meal_id, payload.name, payload.servings)
    return serializers.meal_read(
        next(m for m in services.meals.list_all() if m.id == meal_id),
        services.meals.list_ingredients(meal_id),
    )


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(meal_id: int, services: Services = Depends(get_services)) -> Response:
    """Delete a meal, its ingredient links, and its day assignments."""
    services.meals.delete(meal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{meal_id}/ingredients", response_model=MealRead)
def add_ingredient(
    meal_id: int, payload: IngredientAdd, services: Services = Depends(get_services)
) -> MealRead:
    """Attach an ingredient, creating it if the name is new."""
    services.meals.add_ingredient(meal_id, payload.name, payload.qty, payload.unit)
    return serializers.meal_read(
        next(m for m in services.meals.list_all() if m.id == meal_id),
        services.meals.list_ingredients(meal_id),
    )


@router.patch("/{meal_id}/ingredients/{ingredient_id}", response_model=MealRead)
def update_ingredient(
    meal_id: int,
    ingredient_id: int,
    payload: IngredientUpdate,
    services: Services = Depends(get_services),
) -> MealRead:
    """Overwrite the quantity and unit of one ingredient on a meal."""
    services.meals.update_ingredient(
        meal_id, ingredient_id, payload.qty, payload.unit
    )
    return serializers.meal_read(
        next(m for m in services.meals.list_all() if m.id == meal_id),
        services.meals.list_ingredients(meal_id),
    )


@router.delete("/{meal_id}/ingredients/{ingredient_id}", response_model=MealRead)
def remove_ingredient(
    meal_id: int, ingredient_id: int, services: Services = Depends(get_services)
) -> MealRead:
    """Detach an ingredient from a meal, leaving the ingredient itself."""
    services.meals.remove_ingredient(meal_id, ingredient_id)
    return serializers.meal_read(
        next(m for m in services.meals.list_all() if m.id == meal_id),
        services.meals.list_ingredients(meal_id),
    )
