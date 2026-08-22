from sqlalchemy import func
from sqlmodel import select
from app.db import get_session
from app.models import Meal, Ingredient
from app.models import WeeklyPlan
from app.models import MealIngredient


def add_meal(name: str, servings: int = 1):
    with get_session() as session:
        existing = session.exec(
            select(Meal).where(func.lower(Meal.name) == name.lower())
        ).first()
        if existing:
            raise ValueError(f"A meal named '{existing.name}' already exists.")

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
        # check if ingredient exists (case-insensitively, so "Eggs" and
        # "eggs" reuse the same ingredient instead of fragmenting the
        # grocery list into duplicate line items)
        ingredient = session.exec(
            select(Ingredient).where(func.lower(Ingredient.name) == ingredient_name.lower())
        ).first()
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

def update_meal(meal_id: int, name: str, servings: int):
    with get_session() as session:
        meal = session.get(Meal, meal_id)
        if not meal:
            return

        if name.lower() != meal.name.lower():
            existing = session.exec(
                select(Meal).where(func.lower(Meal.name) == name.lower(), Meal.id != meal_id)
            ).first()
            if existing:
                raise ValueError(f"A meal named '{existing.name}' already exists.")

        meal.name = name
        meal.servings = servings
        session.commit()

def update_meal_ingredient(meal_id: int, ingredient_id: int, qty: float, unit: str):
    with get_session() as session:
        link = session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id
            )
        ).first()
        if link:
            link.qty = qty
            link.unit = unit
            session.commit()

def delete_meal(meal_id: int):
    with get_session() as session:
        meal = session.get(Meal, meal_id)
        if not meal:
            return

        links = session.exec(
            select(MealIngredient).where(MealIngredient.meal_id == meal_id)
        ).all()
        for link in links:
            session.delete(link)

        plans = session.exec(
            select(WeeklyPlan).where(WeeklyPlan.meal_id == meal_id)
        ).all()
        for plan in plans:
            plan.meal_id = None

        session.delete(meal)
        session.commit()

def get_meal_ingredients(meal_id: int):
    with get_session() as session:
        statement = (
            select(MealIngredient, Ingredient)
            .where(MealIngredient.meal_id == meal_id)
            .where(MealIngredient.ingredient_id == Ingredient.id)
        )
        return session.exec(statement).all()

def remove_ingredient_from_meal(meal_id: int, ingredient_id: int):
    with get_session() as session:
        link = session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id
            )
        ).first()
        if link:
            session.delete(link)
            session.commit()

def set_meal_for_day(week_start_date, day: str, meal_id: int):
    with get_session() as session:
        plan = session.exec(
            select(WeeklyPlan).where(
                WeeklyPlan.week_start_date == week_start_date,
                WeeklyPlan.day_of_week == day,
            )
        ).first()
        if plan:
            plan.meal_id = meal_id
        else:
            plan = WeeklyPlan(week_start_date=week_start_date, day_of_week=day, meal_id=meal_id)
            session.add(plan)
        session.commit()

def get_weekly_plan(week_start_date):
    with get_session() as session:
        statement = select(WeeklyPlan).where(WeeklyPlan.week_start_date == week_start_date)
        plans = session.exec(statement).all()
        return plans