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
        weekly = session.exec(select(WeeklyPlan)).all()

        for plan in weekly:
            meal_id = plan.meal_id
            if not meal_id:
                continue

            links = session.exec(
                select(MealIngredient).where(MealIngredient.meal_id == meal_id)
            ).all()

            for link in links:
                name = session.get(Ingredient, link.ingredient_id).name
                unit = link.unit if link.unit else ""
                qty = link.qty if link.qty else 0

                if name not in grocery:
                    grocery[name] = {"qty": qty, "unit": unit}
                else:
                    # merge quantities if unit matches
                    if grocery[name]["unit"] == unit:
                        grocery[name]["qty"] += qty
                    else:
                        # simple fallback: keep as separate entries (advanced: normalize units)
                        grocery[f"{name} ({unit})"] = {"qty": qty, "unit": unit}

    # convert to display format
    return {k: f'{v["qty"]} {v["unit"]}'.strip() for k,v in grocery.items()}