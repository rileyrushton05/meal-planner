from sqlmodel import select
from app.db import get_session
from app.models import Meal, Ingredient


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