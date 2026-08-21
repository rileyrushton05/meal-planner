import pytest

from app.crud import (
    add_meal,
    get_meals,
    add_ingredient,
    get_ingredients,
    add_ingredient_to_meal,
    get_meal_ingredients,
    remove_ingredient_from_meal,
    update_meal,
    update_meal_ingredient,
    delete_meal,
    set_meal_for_day,
    get_weekly_plan,
)


def test_add_meal_creates_a_meal():
    meal = add_meal("Spaghetti", servings=4)

    assert meal.id is not None
    assert meal.servings == 4
    assert [m.name for m in get_meals()] == ["Spaghetti"]


def test_add_meal_rejects_duplicate_name():
    add_meal("Spaghetti")

    with pytest.raises(ValueError):
        add_meal("Spaghetti")

    assert len(get_meals()) == 1


def test_add_ingredient_to_meal_creates_ingredient_and_link():
    meal = add_meal("Spaghetti")

    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")

    ingredients = get_meal_ingredients(meal.id)
    assert len(ingredients) == 1
    link, ingredient = ingredients[0]
    assert ingredient.name == "Pasta"
    assert link.qty == 200
    assert link.unit == "g"
    assert [i.name for i in get_ingredients()] == ["Pasta"]


def test_add_ingredient_to_meal_reuses_existing_ingredient_by_name():
    meal_a = add_meal("Spaghetti")
    meal_b = add_meal("Garlic Bread")
    add_ingredient("Pasta")

    add_ingredient_to_meal(meal_a.id, "Pasta", 200, "g")
    add_ingredient_to_meal(meal_b.id, "Pasta", 100, "g")

    assert len(get_ingredients()) == 1


def test_add_ingredient_to_meal_accumulates_matching_unit():
    meal = add_meal("Spaghetti")

    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    add_ingredient_to_meal(meal.id, "Pasta", 100, "g")

    link, _ = get_meal_ingredients(meal.id)[0]
    assert link.qty == 300


def test_add_ingredient_to_meal_rejects_mismatched_unit():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")

    with pytest.raises(ValueError):
        add_ingredient_to_meal(meal.id, "Pasta", 1, "cup")

    link, _ = get_meal_ingredients(meal.id)[0]
    assert link.qty == 200


def test_remove_ingredient_from_meal():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    ingredient_id = get_meal_ingredients(meal.id)[0][1].id

    remove_ingredient_from_meal(meal.id, ingredient_id)

    assert get_meal_ingredients(meal.id) == []


def test_delete_meal_removes_ingredient_links_and_unassigns_plan():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    set_meal_for_day("Monday", meal.id)

    delete_meal(meal.id)

    assert get_meals() == []
    plan = {p.day_of_week: p.meal_id for p in get_weekly_plan()}
    assert plan["Monday"] is None


def test_set_meal_for_day_updates_existing_day_instead_of_duplicating():
    meal_a = add_meal("Spaghetti")
    meal_b = add_meal("Chicken Stir Fry")

    set_meal_for_day("Monday", meal_a.id)
    set_meal_for_day("Monday", meal_b.id)

    plans = [p for p in get_weekly_plan() if p.day_of_week == "Monday"]
    assert len(plans) == 1
    assert plans[0].meal_id == meal_b.id


def test_update_meal_changes_name_and_servings():
    meal = add_meal("Spaghetti", servings=1)

    update_meal(meal.id, "Spaghetti Bolognese", 4)

    updated = get_meals()[0]
    assert updated.name == "Spaghetti Bolognese"
    assert updated.servings == 4


def test_update_meal_rejects_renaming_to_an_existing_meal_name():
    meal_a = add_meal("Spaghetti")
    meal_b = add_meal("Chicken Stir Fry")

    with pytest.raises(ValueError):
        update_meal(meal_b.id, "Spaghetti", meal_b.servings)

    assert get_meals()[1].name == "Chicken Stir Fry"


def test_update_meal_allows_keeping_the_same_name():
    meal = add_meal("Spaghetti", servings=1)

    update_meal(meal.id, "Spaghetti", 2)

    assert get_meals()[0].servings == 2


def test_update_meal_ingredient_changes_quantity_and_unit():
    meal = add_meal("Spaghetti")
    add_ingredient_to_meal(meal.id, "Pasta", 200, "g")
    ingredient_id = get_meal_ingredients(meal.id)[0][1].id

    update_meal_ingredient(meal.id, ingredient_id, 500, "kg")

    link, _ = get_meal_ingredients(meal.id)[0]
    assert link.qty == 500
    assert link.unit == "kg"
