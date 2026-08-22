from sqlmodel import select
from app.db import get_session
from app.models import WeeklyPlan, MealIngredient, Ingredient

# Unambiguous unit conversions, normalized to a base unit per family, so
# e.g. "200 g" and "0.5 kg" of the same ingredient merge into one grocery
# line instead of two. Deliberately excludes tsp/tbsp/cup - their actual
# size varies by region (an Australian metric cup is 250 ml, a US cup is
# ~237 ml), so auto-converting them risks silently producing a wrong
# quantity rather than just failing to merge.
UNIT_CONVERSIONS = {
    "mg": ("g", 0.001),
    "g": ("g", 1),
    "kg": ("g", 1000),
    "ml": ("ml", 1),
    "l": ("ml", 1000),
}


def _normalize_unit(qty, unit):
    unit_key = (unit or "").strip().lower()
    if unit_key in UNIT_CONVERSIONS:
        base_unit, factor = UNIT_CONVERSIONS[unit_key]
        return qty * factor, base_unit
    return qty, unit_key


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
                qty, unit = _normalize_unit(link.qty if link.qty else 0, link.unit)

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