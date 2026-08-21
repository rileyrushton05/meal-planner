from sqlmodel import select
from app.db import get_session
from app.models import Meal, Ingredient
from app.models import WeeklyPlan
from app.models import MealIngredient


def add_meal(name: str, servings: int = 1):
    with get_session() as session:
        meal = Meal(name=name, servings=servings)
        session.add(meal)
        session.commit()
        session.refresh(meal)
        return meal

def get_meals():
    with get_session() as session:
        statement = select(Meal)
        meals = session.exec(statement).all()
        return meals

def get_ingredients():
    with get_session() as session:
        statement = select(Ingredient)
        ingredients = session.exec(statement).all()
        return ingredients

def add_ingredient(name: str):
    with get_session() as session:
        ingredient = Ingredient(name=name)
        session.add(ingredient)
        session.commit()
        session.refresh(ingredient)
        return ingredient

def add_ingredient_to_meal(meal_id: int, ingredient_name: str, qty: float, unit: str):
    with get_session() as session:
        # check if ingredient exists
        ingredient = session.exec(select(Ingredient).where(Ingredient.name == ingredient_name)).first()
        if not ingredient:
            ingredient = add_ingredient(ingredient_name)
        
        # check if this meal already has the ingredient
        existing_link = session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient.id
            )
        ).first()

        if existing_link:
            if existing_link.unit != unit:
                raise ValueError(
                    f"{ingredient_name} is already on this meal measured in "
                    f"'{existing_link.unit}'. Use the same unit to add more, "
                    f"or remove the existing entry first."
                )
            existing_link.qty = (existing_link.qty or 0) + qty
        else:
            link = MealIngredient(
                meal_id=meal_id,
                ingredient_id=ingredient.id,
                qty=qty,
                unit=unit
            )
            session.add(link)

        session.commit()

def set_meal_for_day(day: str, meal_id: int):
    with get_session() as session:
        plan = session.exec(
            select(WeeklyPlan).where(WeeklyPlan.day_of_week == day)  
        ).first()
        if plan:
            plan.meal_id = meal_id
        else:
            plan = WeeklyPlan(day_of_week=day, meal_id=meal_id) 
            session.add(plan)
        session.commit()

def get_weekly_plan():
    with get_session() as session:
        statement = select(WeeklyPlan)
        plans = session.exec(statement).all()
        return plans