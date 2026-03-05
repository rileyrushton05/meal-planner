from sqlmodel import select
from app.db import get_session
from app.models import WeeklyPlan, MealIngredient, Ingredient

def generate_weekly_grocery_list():
    """
    Reads all meals assigned to days, collects ingredients,
    merges duplicates, and returns a dictionary {ingredient_name: total_qty}
    """
    grocery = {}

    with get_session() as session:
        # Get all weekly plans
        weekly = session.exec(select(WeeklyPlan)).all()

        for plan in weekly:
            meal_id = plan.meal_id
            if not meal_id:
                continue

            # Get all ingredients for this meal
            links = session.exec(
                select(MealIngredient).where(MealIngredient.meal_id == meal_id)
            ).all()

            for link in links:
                ingredient = session.get(Ingredient, link.ingredient_id)
                if ingredient.name not in grocery:
                    grocery[ingredient.name] = link.qty
                else:
                    grocery[ingredient.name] += link.qty

    return grocery