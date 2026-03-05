from sqlmodel import select
from app.db import get_session
from app.models import MealIngredient, Ingredient


def generate_grocery_list(meal_ids):
    grocery = {}

    with get_session() as session:

        for meal_id in meal_ids:

            statement = select(MealIngredient).where(MealIngredient.meal_id == meal_id)
            links = session.exec(statement).all()

            for link in links:

                ingredient = session.get(Ingredient, link.ingredient_id)

                if ingredient.name not in grocery:
                    grocery[ingredient.name] = link.qty
                else:
                    grocery[ingredient.name] += link.qty

    return grocery