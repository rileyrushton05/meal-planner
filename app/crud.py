from sqlmodel import select
from app.db import get_session
from app.models import Meal, Ingredient
from app.models import WeeklyPlan


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


def add_ingredient(name: str):
    with get_session() as session:
        ingredient = Ingredient(name=name)
        session.add(ingredient)
        session.commit()
        session.refresh(ingredient)
        return ingredient


def get_ingredients():
    with get_session() as session:
        statement = select(Ingredient)
        ingredients = session.exec(statement).all()
        return ingredients
    
def set_meal_for_day(day: str, meal_id: int):
    with get_session() as session:

        existing = session.exec(
            select(WeeklyPlan).where(WeeklyPlan.day_of_week == day)
        ).first()

        if existing:
            existing.meal_id = meal_id
        else:
            plan = WeeklyPlan(day_of_week=day, meal_id=meal_id)
            session.add(plan)

        session.commit()

def get_weekly_plan():
    with get_session() as session:
        statement = select(WeeklyPlan)
        plans = session.exec(statement).all()
        return plans