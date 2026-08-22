from sqlmodel import select
from app.db import get_session
from app.models import WeeklyPlan, MealIngredient, Ingredient

def generate_weekly_grocery_list(week_start_date):
    """
    Reads all meals assigned to days in the given week, collects ingredients,
    merges duplicates, and returns a dictionary {ingredient_name: total_qty}
    """
    # accumulate by (name, unit) so no combination is ever overwritten
    grocery = {}

    with get_session() as session:
        weekly = session.exec(
            select(WeeklyPlan).where(WeeklyPlan.week_start_date == week_start_date)
        ).all()

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

                key = (name, unit)
                grocery[key] = grocery.get(key, 0) + qty

    # only disambiguate with the unit when an ingredient has more than
    # one unit variant across the week's meals
    name_counts = {}
    for name, unit in grocery:
        name_counts[name] = name_counts.get(name, 0) + 1

    result = {}
    for (name, unit), qty in grocery.items():
        label = name if name_counts[name] == 1 else f"{name} ({unit})"
        result[label] = f"{qty} {unit}".strip()

    return result