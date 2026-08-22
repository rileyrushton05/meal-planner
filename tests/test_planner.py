from datetime import date

from app.crud import add_meal, add_ingredient_to_meal, set_meal_for_day
from app.planner import generate_weekly_grocery_list

WEEK_1 = date(2026, 8, 3)
WEEK_2 = date(2026, 8, 10)


def test_empty_plan_produces_empty_list():
    assert generate_weekly_grocery_list(WEEK_1) == {}


def test_single_day_single_ingredient():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    set_meal_for_day(WEEK_1, "Monday", meal.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "200.0 g"}


def test_same_meal_on_multiple_days_sums_quantities():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    set_meal_for_day(WEEK_1, "Monday", meal.id)
    set_meal_for_day(WEEK_1, "Thursday", meal.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "400.0 g"}


def test_matching_unit_across_meals_merges_into_one_entry():
    meal_a = add_meal("Spaghetti")
    meal_b = add_meal("Garlic Bread")
    add_ingredient_to_meal(meal_a.id, "Butter", 20, "g")
    add_ingredient_to_meal(meal_b.id, "Butter", 30, "g")
    set_meal_for_day(WEEK_1, "Monday", meal_a.id)
    set_meal_for_day(WEEK_1, "Tuesday", meal_b.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Butter": "50.0 g"}


def test_units_outside_the_convertible_families_are_all_kept_not_overwritten():
    meal_a = add_meal("Meal A")
    meal_b = add_meal("Meal B")
    meal_c = add_meal("Meal C")
    add_ingredient_to_meal(meal_a.id, "Milk", 200, "ml")
    add_ingredient_to_meal(meal_b.id, "Milk", 1, "cup")
    add_ingredient_to_meal(meal_c.id, "Milk", 2, "tbsp")
    set_meal_for_day(WEEK_1, "Monday", meal_a.id)
    set_meal_for_day(WEEK_1, "Tuesday", meal_b.id)
    set_meal_for_day(WEEK_1, "Wednesday", meal_c.id)

    result = generate_weekly_grocery_list(WEEK_1)

    assert result == {
        "Milk (ml)": "200.0 ml",
        "Milk (cup)": "1.0 cup",
        "Milk (tbsp)": "2.0 tbsp",
    }


def test_convertible_units_merge_via_their_base_unit():
    meal_a = add_meal("Meal A")
    meal_b = add_meal("Meal B")
    meal_c = add_meal("Meal C")
    add_ingredient_to_meal(meal_a.id, "Milk", 200, "ml")
    add_ingredient_to_meal(meal_b.id, "Milk", 2, "L")
    add_ingredient_to_meal(meal_c.id, "Flour", 300, "g")
    set_meal_for_day(WEEK_1, "Monday", meal_a.id)
    set_meal_for_day(WEEK_1, "Tuesday", meal_b.id)
    set_meal_for_day(WEEK_1, "Wednesday", meal_c.id)

    result = generate_weekly_grocery_list(WEEK_1)

    assert result == {"Milk": "2200.0 ml", "Flour": "300.0 g"}


def test_unit_case_is_normalized_even_when_not_convertible():
    meal_a = add_meal("Meal A")
    meal_b = add_meal("Meal B")
    add_ingredient_to_meal(meal_a.id, "Sugar", 1, "Tbsp")
    add_ingredient_to_meal(meal_b.id, "Sugar", 2, "tbsp")
    set_meal_for_day(WEEK_1, "Monday", meal_a.id)
    set_meal_for_day(WEEK_1, "Tuesday", meal_b.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Sugar": "3.0 tbsp"}


def test_planned_servings_scales_ingredient_quantities():
    meal = add_meal("Spaghetti", servings=4)
    add_ingredient_to_meal(meal.id, "Pasta", 400, "g")
    set_meal_for_day(WEEK_1, "Monday", meal.id, servings=2)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "200.0 g"}


def test_no_planned_servings_uses_recipe_quantity_unscaled():
    meal = add_meal("Spaghetti", servings=4)
    add_ingredient_to_meal(meal.id, "Pasta", 400, "g")
    set_meal_for_day(WEEK_1, "Monday", meal.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "400.0 g"}


def test_unassigned_day_is_ignored():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    set_meal_for_day(WEEK_1, "Monday", meal.id)
    set_meal_for_day(WEEK_1, "Tuesday", None)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "200.0 g"}


def test_grocery_list_is_scoped_to_its_week():
    meal_a = add_meal("Spaghetti")
    meal_b = add_meal("Chicken Stir Fry")
    add_ingredient_to_meal(meal_a.id, "Pasta", 200, "g")
    add_ingredient_to_meal(meal_b.id, "Rice", 300, "g")
    set_meal_for_day(WEEK_1, "Monday", meal_a.id)
    set_meal_for_day(WEEK_2, "Monday", meal_b.id)

    assert generate_weekly_grocery_list(WEEK_1) == {"Pasta": "200.0 g"}
    assert generate_weekly_grocery_list(WEEK_2) == {"Rice": "300.0 g"}
