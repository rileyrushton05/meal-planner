"""Tests for the data-access layer."""

from __future__ import annotations

from datetime import date

import pytest

from app.exceptions import (
    DuplicateNameError,
    IngredientNotOnMealError,
    InvalidDayError,
    MealNotFoundError,
    UnitMismatchError,
)
from app.models import DayOfWeek
from app.templates import MealTemplate, TemplateIngredient

WEEK_1 = date(2026, 8, 3)
WEEK_2 = date(2026, 8, 10)


# ------------------------------------------------------------------ meals


def test_add_creates_a_meal(meals):
    meal = meals.add("Spaghetti", servings=4)

    assert meal.id is not None
    assert meal.servings == 4
    assert [m.name for m in meals.list_all()] == ["Spaghetti"]


def test_add_rejects_duplicate_name(meals):
    meals.add("Spaghetti")

    with pytest.raises(DuplicateNameError):
        meals.add("Spaghetti")

    assert len(meals.list_all()) == 1


def test_add_rejects_duplicate_name_case_insensitively(meals):
    meals.add("Spaghetti")

    with pytest.raises(DuplicateNameError):
        meals.add("spaghetti")

    assert len(meals.list_all()) == 1


def test_update_changes_name_and_servings(meals):
    meal = meals.add("Spaghetti", servings=1)

    meals.update(meal.id, "Spaghetti Bolognese", 4)

    updated = meals.list_all()[0]
    assert updated.name == "Spaghetti Bolognese"
    assert updated.servings == 4


def test_update_rejects_renaming_onto_another_meal(meals):
    meals.add("Spaghetti")
    other = meals.add("Chicken Stir Fry")

    with pytest.raises(DuplicateNameError):
        meals.update(other.id, "SPAGHETTI", other.servings)

    assert meals.list_all()[1].name == "Chicken Stir Fry"


def test_update_allows_changing_only_the_casing_of_its_own_name(meals):
    meal = meals.add("spaghetti", servings=1)

    meals.update(meal.id, "Spaghetti", 1)

    assert meals.list_all()[0].name == "Spaghetti"


def test_update_missing_meal_raises(meals):
    with pytest.raises(MealNotFoundError):
        meals.update(999, "Nope", 1)


def test_delete_missing_meal_raises(meals):
    with pytest.raises(MealNotFoundError):
        meals.delete(999)


def test_delete_removes_ingredient_links_and_unassigns_plan(meals, plans):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)

    meals.delete(meal.id)

    assert meals.list_all() == []
    by_day = {plan.day_of_week: plan.meal_id for plan in plans.get_week(WEEK_1)}
    assert by_day["Monday"] is None


# ------------------------------------------------------------ ingredients


def test_add_ingredient_creates_ingredient_and_link(meals, ingredients):
    meal = meals.add("Spaghetti")

    meals.add_ingredient(meal.id, "Pasta", 200, "g")

    attached = meals.list_ingredients(meal.id)
    assert len(attached) == 1
    link, ingredient = attached[0]
    assert ingredient.name == "Pasta"
    assert link.qty == 200
    assert link.unit == "g"
    assert [i.name for i in ingredients.list_all()] == ["Pasta"]


def test_add_ingredient_reuses_the_same_ingredient_across_meals(meals, ingredients):
    first = meals.add("Spaghetti")
    second = meals.add("Garlic Bread")

    meals.add_ingredient(first.id, "Garlic", 2, "cloves")
    meals.add_ingredient(second.id, "Garlic", 1, "cloves")

    assert len(ingredients.list_all()) == 1


def test_add_ingredient_reuses_ingredient_regardless_of_case(meals, ingredients):
    first = meals.add("Spaghetti")
    second = meals.add("Garlic Bread")

    meals.add_ingredient(first.id, "Eggs", 2, "")
    meals.add_ingredient(second.id, "eggs", 3, "")

    assert [i.name for i in ingredients.list_all()] == ["Eggs"]


def test_add_ingredient_accumulates_when_units_match(meals):
    meal = meals.add("Spaghetti")

    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    meals.add_ingredient(meal.id, "Pasta", 100, "g")

    link, _ = meals.list_ingredients(meal.id)[0]
    assert link.qty == 300


def test_add_ingredient_rejects_a_mismatched_unit(meals):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")

    with pytest.raises(UnitMismatchError):
        meals.add_ingredient(meal.id, "Pasta", 1, "cup")

    link, _ = meals.list_ingredients(meal.id)[0]
    assert link.qty == 200


def test_update_ingredient_changes_quantity_and_unit(meals):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    ingredient_id = meals.list_ingredients(meal.id)[0][1].id

    meals.update_ingredient(meal.id, ingredient_id, 500, "kg")

    link, _ = meals.list_ingredients(meal.id)[0]
    assert link.qty == 500
    assert link.unit == "kg"


def test_remove_ingredient_detaches_it_from_the_meal(meals, ingredients):
    meal = meals.add("Spaghetti")
    meals.add_ingredient(meal.id, "Pasta", 200, "g")
    ingredient_id = meals.list_ingredients(meal.id)[0][1].id

    meals.remove_ingredient(meal.id, ingredient_id)

    assert meals.list_ingredients(meal.id) == []
    # The ingredient itself survives, since other meals may still use it.
    assert [i.name for i in ingredients.list_all()] == ["Pasta"]


# -------------------------------------------------------------- templates


def test_add_from_template_creates_meal_and_all_ingredients(meals):
    template = MealTemplate(
        name="Omelette",
        servings=1,
        ingredients=(
            TemplateIngredient("Eggs", 3),
            TemplateIngredient("Cheese", 50, "g"),
        ),
    )

    meals.add_from_template(template)

    meal = meals.list_all()[0]
    assert meal.name == "Omelette"
    assert {i.name for _, i in meals.list_ingredients(meal.id)} == {"Eggs", "Cheese"}


def test_add_from_template_rolls_back_entirely_on_failure(meals):
    """A template that fails part-way must not leave a half-built meal."""
    template = MealTemplate(
        name="Broken",
        servings=1,
        ingredients=(
            TemplateIngredient("Flour", 100, "g"),
            # Same ingredient, incompatible unit: raises once the first is
            # already staged in the transaction.
            TemplateIngredient("Flour", 1, "cup"),
        ),
    )

    with pytest.raises(UnitMismatchError):
        meals.add_from_template(template)

    assert meals.list_all() == []


# ----------------------------------------------------------- weekly plans


def test_set_day_updates_the_existing_day_rather_than_duplicating(meals, plans):
    first = meals.add("Spaghetti")
    second = meals.add("Chicken Stir Fry")

    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, second.id)

    monday = [p for p in plans.get_week(WEEK_1) if p.day_of_week == "Monday"]
    assert len(monday) == 1
    assert monday[0].meal_id == second.id


def test_set_day_is_scoped_to_its_week(meals, plans):
    first = meals.add("Spaghetti")
    second = meals.add("Chicken Stir Fry")

    plans.set_day(WEEK_1, DayOfWeek.MONDAY, first.id)
    plans.set_day(WEEK_2, DayOfWeek.MONDAY, second.id)

    week_1 = {p.day_of_week: p.meal_id for p in plans.get_week(WEEK_1)}
    week_2 = {p.day_of_week: p.meal_id for p in plans.get_week(WEEK_2)}
    assert week_1["Monday"] == first.id
    assert week_2["Monday"] == second.id


def test_copy_week_carries_assignments_forward(meals, plans):
    meal = meals.add("Spaghetti", servings=4)
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id, servings=2)

    copied = plans.copy_week(WEEK_1, WEEK_2)

    assert copied == 1
    target = {p.day_of_week: p for p in plans.get_week(WEEK_2)}
    assert target["Monday"].meal_id == meal.id
    assert target["Monday"].servings == 2


def test_copy_week_reports_nothing_copied_for_an_empty_source(plans):
    assert plans.copy_week(WEEK_1, WEEK_2) == 0
    assert plans.get_week(WEEK_2) == []


def test_copy_week_skips_unset_days_instead_of_clearing_the_target(meals, plans):
    meal = meals.add("Spaghetti")
    plans.set_day(WEEK_1, DayOfWeek.MONDAY, meal.id)
    plans.set_day(WEEK_1, DayOfWeek.TUESDAY, None)
    plans.set_day(WEEK_2, DayOfWeek.TUESDAY, meal.id)

    plans.copy_week(WEEK_1, WEEK_2)

    target = {p.day_of_week: p.meal_id for p in plans.get_week(WEEK_2)}
    assert target["Monday"] == meal.id
    assert target["Tuesday"] == meal.id


def test_updating_an_unattached_ingredient_raises(meals):
    meal = meals.add("Spaghetti")

    with pytest.raises(IngredientNotOnMealError):
        meals.update_ingredient(meal.id, 999, qty=5, unit="g")


def test_removing_an_unattached_ingredient_raises(meals):
    meal = meals.add("Spaghetti")

    with pytest.raises(IngredientNotOnMealError):
        meals.remove_ingredient(meal.id, 999)


def test_a_day_that_is_not_a_weekday_is_rejected(plans):
    """The column is a plain string, so the guard lives in the repository
    rather than relying on the database to reject it."""
    with pytest.raises(InvalidDayError):
        plans.set_day(WEEK_1, "Funday", meal_id=None)

    assert plans.get_week(WEEK_1) == []
