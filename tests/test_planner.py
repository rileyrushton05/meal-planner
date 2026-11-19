"""Tests for grocery list aggregation."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app import jobs, units
from app.models import DayOfWeek
from app.planner import generate_weekly_grocery_list

WEEK_1 = date(2026, 8, 3)
WEEK_2 = date(2026, 8, 10)


def as_pairs(items) -> dict[str, str]:
    """Collapse a grocery list to {name: displayed amount} for assertions."""
    return {item.name: item.display_qty for item in items}


def test_empty_plan_produces_empty_list(plans):
    assert generate_weekly_grocery_list(plans, WEEK_1) == []


def test_single_day_single_ingredient(meals, plans):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "200 g"}


def test_same_meal_on_multiple_days_sums_quantities(meals, plans):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)
    plans.set_day(WEEK_1, DayOfWeek.THURSDAY, meal.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "400 g"}


def test_matching_unit_across_meals_merges_into_one_entry(meals, plans):
    first = meals.add("Spaghetti")
    second = meals.add("Garlic Bread")
    meals.add_ingredient(first.id, "Butter", 20, "g")
    meals.add_ingredient(second.id, "Butter", 30, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, second.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Butter": "50 g"}


def test_convertible_units_merge_via_their_base_unit(meals, plans):
    first = meals.add("Meal A")
    second = meals.add("Meal B")
    meals.add_ingredient(first.id, "Milk", 200, "ml")
    meals.add_ingredient(second.id, "Milk", 2, "L")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, second.id)

    # Summed in millilitres, then shown in the unit a shopper would use.
    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Milk": "2.2 L"}


def test_inconvertible_units_stay_as_separate_lines(meals, plans):
    first = meals.add("Meal A")
    second = meals.add("Meal B")
    meals.add_ingredient(first.id, "Milk", 200, "ml")
    meals.add_ingredient(second.id, "Milk", 1, "cup")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, second.id)

    items = generate_weekly_grocery_list(plans, WEEK_1)

    assert [(i.name, i.display_qty) for i in items] == [
        ("Milk", "1 cup"),
        ("Milk", "200 ml"),
    ]


def test_unit_case_is_normalized_even_when_not_convertible(meals, plans):
    first = meals.add("Meal A")
    second = meals.add("Meal B")
    meals.add_ingredient(first.id, "Sugar", 1, "Tbsp")
    meals.add_ingredient(second.id, "Sugar", 2, "tbsp")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, second.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Sugar": "3 tbsp"}


def test_count_based_ingredients_render_without_a_unit(meals, plans):
    meal = meals.add("Omelette")
    meals.add_ingredient(meal.id, "Eggs", 3, "")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Eggs": "3"}


def test_planned_servings_scale_ingredient_quantities(meals, plans):
    meal = meals.add("Spaghetti", servings=4)
    meals.add_ingredient(meal.id, "Pasta", 400, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id, servings=2)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "200 g"}


def test_no_planned_servings_uses_the_recipe_unscaled(meals, plans):
    meal = meals.add("Spaghetti", servings=4)
    meals.add_ingredient(meal.id, "Pasta", 400, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "400 g"}


def test_unassigned_day_is_ignored(meals, plans):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, None)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "200 g"}


def test_grocery_list_is_scoped_to_its_week(meals, plans):
    first = meals.add("Spaghetti")
    second = meals.add("Chicken Stir Fry")
    meals.add_ingredient(first.id, "Pasta", 200, "g")
    meals.add_ingredient(second.id, "Rice", 300, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_2, DayOfWeek.MONDAY, second.id)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Pasta": "200 g"}
    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_2)) == {"Rice": "300 g"}


def test_results_are_sorted_by_ingredient_name(meals, plans):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Zucchini", 1, "")
    meals.add_ingredient(meal.id, "Apple", 2, "")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    names = [item.name for item in generate_weekly_grocery_list(plans, WEEK_1)]
    assert names == sorted(names)


# --- Counted things are bought whole --------------------------------------------


def test_half_a_counted_item_is_one_to_buy(meals, plans):
    """A recipe for four planned for two needs half a lettuce: buy one."""
    meal = meals.add("Caesar Salad", servings=4)
    meals.add_ingredient(meal.id, "Lettuce", 1, "")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id, servings=2)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Lettuce": "1"}


def test_counted_items_are_rounded_up_only_once_totalled(meals, plans):
    """Half a lettuce on two nights is one lettuce, not two."""
    meal = meals.add("Caesar Salad", servings=4)
    meals.add_ingredient(meal.id, "Lettuce", 1, "")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id, servings=2)
    plans.set_day(WEEK_1, DayOfWeek.FRIDAY, meal.id, servings=2)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {"Lettuce": "1"}


def test_counted_units_round_up_and_measures_do_not(meals, plans):
    meal = meals.add("Chilli", servings=4)
    meals.add_ingredient(meal.id, "Kidney Beans", 1, "cans")
    meals.add_ingredient(meal.id, "Garlic", 3, "cloves")
    meals.add_ingredient(meal.id, "Rice", 1, "cups")
    meals.add_ingredient(meal.id, "Beef Mince", 500, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id, servings=2)

    assert as_pairs(generate_weekly_grocery_list(plans, WEEK_1)) == {
        "Kidney Beans": "1 can",
        "Garlic": "2 cloves",
        "Rice": "0.5 cups",
        "Beef Mince": "250 g",
    }


def test_to_buy_rounds_only_counted_units() -> None:
    assert units.to_buy(0.5, "") == 1
    assert units.to_buy(1.5, "bunches") == 2
    # A total floating point left a hair over a whole number is that number.
    assert 0.1 * 3 * 10 > 3
    assert units.to_buy(0.1 * 3 * 10, "") == 3
    assert units.to_buy(0.5, "tbsp") == 0.5
    assert units.to_buy(250, "g") == 250


# --- Aisles ---------------------------------------------------------------------


def test_lines_come_in_aisle_order_with_the_unknown_last(db, meals, plans):
    with db.transaction() as session:
        jobs.sync_catalog(
            session, now=datetime(2026, 11, 19, tzinfo=UTC), dry_run=False
        )
    meal = meals.add("Everything")
    for name in ("Frozen Peas", "Dragon Fruit", "Milk", "Pasta", "Onion", "Bacon"):
        meals.add_ingredient(meal.id, name, 1, "")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    items = generate_weekly_grocery_list(plans, WEEK_1)

    assert [(item.name, item.category) for item in items] == [
        ("Onion", "produce"),
        ("Bacon", "meat"),
        ("Milk", "dairy"),
        ("Pasta", "pantry"),
        ("Frozen Peas", "frozen"),
        ("Dragon Fruit", None),
    ]
