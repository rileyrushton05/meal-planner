"""End-to-end tests driving the Streamlit widget tree.

These exercise the app the way a user does — clicking buttons and filling
fields — rather than calling repositories directly, so wiring mistakes
between the UI and the data layer get caught.
"""

from __future__ import annotations

from datetime import timedelta

from streamlit.testing.v1 import AppTest

from app.templates import MEAL_TEMPLATES

APP_FILE = "ui/streamlit_app.py"


def run_app() -> AppTest:
    at = AppTest.from_file(APP_FILE)
    at.run()
    return at


def _submit_key(at: AppTest, tab_index: int, form_name: str) -> str:
    return [
        widget.key
        for widget in at.tabs[tab_index].button
        if widget.key and widget.key.startswith(f"FormSubmitter:{form_name}")
    ][0]


def _label(at: AppTest, widgets: str, label: str):
    """Fetch a widget by its visible label, for inputs with no explicit key."""
    return [w for w in getattr(at.tabs[0], widgets) if w.label == label][0]


def _add_meal(at: AppTest, name: str, servings: int | None = None) -> None:
    _label(at, "text_input", "Meal name").input(name)
    if servings is not None:
        _label(at, "number_input", "Servings").set_value(servings)
    at.run()
    at.tabs[0].button(key=_submit_key(at, 0, "add_meal_form")).click().run()


def _add_ingredient(
    at: AppTest, meal_name: str, ingredient: str, qty: float, unit: str
) -> None:
    """Add via the plain "type a new one" field, the fully reliable path."""
    at.tabs[0].selectbox(key="ingredient_meal").select(meal_name).run()
    _label(at, "text_input", "...or type a new one").input(ingredient)
    _label(at, "number_input", "Quantity").set_value(qty)
    _label(at, "text_input", "Unit (g, ml, tbsp...)").input(unit)
    at.run()
    at.tabs[0].button(key="add_ingredient_btn").click().run()


def _seed_ingredient_searchbox(at: AppTest, value: str) -> None:
    """Simulate having selected `value` in the autocomplete component.

    AppTest cannot drive a custom component's real typing/selection, so this
    pre-seeds the session_state entry st_searchbox reads its result from
    (matching the shape in that library's source). It covers the Python-side
    handling only, not the in-browser interaction.
    """
    key_name = "ingredient_searchbox_generation"
    generation = at.session_state[key_name] if key_name in at.session_state else 0
    key = f"ingredient_searchbox_{generation}"
    at.session_state[key] = {
        "result": value,
        "search": value,
        "options_js": [],
        "options_py": [],
        "key_react": f"{key}_react_0",
    }


def _plan_monday(at: AppTest, meal_name: str, servings: int | None = None) -> None:
    monday_key = [
        w.key for w in at.tabs[1].selectbox if w.key and w.key.endswith("_Monday")
    ][0]
    at.tabs[1].selectbox(key=monday_key).select(meal_name)
    if servings is not None:
        servings_key = [
            w.key
            for w in at.tabs[1].number_input
            if w.key and w.key.endswith("_Monday") and "servings" in w.key
        ][0]
        at.tabs[1].number_input(key=servings_key).set_value(servings)
    at.run()
    at.tabs[1].button(key=_submit_key(at, 1, "weekly_plan_form")).click().run()


def _generate_grocery_list(at: AppTest) -> None:
    at.tabs[2].button(key=[w.key for w in at.tabs[2].button][0]).click().run()


def _day_card(at: AppTest, short_day: str) -> str:
    cards = [m.value for m in at.tabs[1].markdown if "day-card" in m.value]
    return [card for card in cards if short_day in card][0]


# ------------------------------------------------------------------ meals


def test_app_loads_with_three_tabs():
    at = run_app()

    assert len(at.exception) == 0
    assert len(at.tabs) == 3


def test_add_meal_shows_success_and_appears_in_list(meals):
    at = run_app()

    _add_meal(at, "Spaghetti", servings=4)

    assert len(at.exception) == 0
    assert any("Added Spaghetti" in s.value for s in at.success)
    assert [m.name for m in meals.list_all()] == ["Spaghetti"]
    assert any("serves 4" in m.value for m in at.tabs[0].markdown)


def test_add_duplicate_meal_shows_an_error(meals):
    at = run_app()
    _add_meal(at, "Spaghetti")

    _add_meal(at, "Spaghetti")

    assert len(at.exception) == 0
    assert any("already exists" in e.value for e in at.tabs[0].error)
    assert len(meals.list_all()) == 1


def test_edit_meal_shows_success_message(meals):
    """Verifies the edit-meal save flow reports success.

    Not a true regression test for the past swallowed-message bug: AppTest
    doesn't reproduce that failure for elements inside st.expander (proven
    by reintroducing the bug and watching this still pass). The
    copy-previous-week test below does catch it.
    """
    at = run_app()
    _add_meal(at, "Spaghetti")
    meal_id = meals.list_all()[0].id

    at.tabs[0].text_input(key=f"edit_name_{meal_id}").input("Spaghetti Bolognese")
    at.run()
    at.tabs[0].button(key=f"save_meal_{meal_id}").click().run()

    assert len(at.exception) == 0
    assert any("Meal updated" in s.value for s in at.success)
    assert meals.list_all()[0].name == "Spaghetti Bolognese"


def test_delete_meal_requires_confirmation(meals):
    at = run_app()
    _add_meal(at, "Spaghetti")
    meal_id = meals.list_all()[0].id

    at.tabs[0].button(key=f"delete_meal_{meal_id}").click().run()
    assert meals.list_all() != []  # asking for confirmation must not delete

    at.tabs[0].button(key=f"cancel_delete_{meal_id}").click().run()
    assert meals.list_all() != []  # cancelling must not delete

    at.tabs[0].button(key=f"delete_meal_{meal_id}").click().run()
    at.tabs[0].button(key=f"confirm_delete_{meal_id}").click().run()

    assert len(at.exception) == 0
    assert meals.list_all() == []


# ------------------------------------------------------------ ingredients


def test_add_ingredient_shows_success_and_appears_in_list():
    at = run_app()
    _add_meal(at, "Spaghetti")

    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")

    assert len(at.exception) == 0
    assert any("Pasta added" in s.value for s in at.success)
    assert any("Pasta — 200 g" in m.value for m in at.tabs[0].markdown)


def test_add_ingredient_not_in_autocomplete_still_works():
    """Regression test: a brand new ingredient with no existing match.

    The name field was once a single searchbox that relied on
    typed-but-unselected text being returned. That could only be verified
    by faking the component's return value, and in real use an ingredient
    like "Bread" on a fresh app could not be added at all.
    """
    at = run_app()
    _add_meal(at, "Sandwich")

    _add_ingredient(at, "Sandwich", "Bread", 4, "slices")

    assert len(at.exception) == 0
    assert any("Bread added" in s.value for s in at.success)
    assert any("Bread — 4 slices" in m.value for m in at.tabs[0].markdown)


def test_add_ingredient_rejects_zero_quantity(meals):
    at = run_app()
    _add_meal(at, "Spaghetti")

    _label(at, "text_input", "...or type a new one").input("Pasta")
    at.run()
    at.tabs[0].button(key="add_ingredient_btn").click().run()

    assert len(at.exception) == 0
    assert any("quantity greater than 0" in e.value for e in at.tabs[0].error)
    assert meals.list_ingredients(meals.list_all()[0].id) == []


def test_add_ingredient_via_searchbox_reuses_existing_ingredient(ingredients):
    """Covers picking an existing ingredient rather than typing a new one."""
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_meal(at, "Garlic Bread")
    _add_ingredient(at, "Spaghetti", "Garlic", 2, "cloves")

    at.tabs[0].selectbox(key="ingredient_meal").select("Garlic Bread").run()
    _seed_ingredient_searchbox(at, "Garlic")
    _label(at, "number_input", "Quantity").set_value(1)
    _label(at, "text_input", "Unit (g, ml, tbsp...)").input("cloves")
    at.run()
    at.tabs[0].button(key="add_ingredient_btn").click().run()

    assert len(at.exception) == 0
    assert any("Garlic added" in s.value for s in at.success)
    assert [i.name for i in ingredients.list_all()] == ["Garlic"]


def test_add_ingredient_with_mismatched_unit_shows_an_error():
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")

    _add_ingredient(at, "Spaghetti", "Pasta", 1, "cup")

    assert len(at.exception) == 0
    assert any("already on this meal" in e.value for e in at.tabs[0].error)


def test_edit_ingredient_shows_success_message(meals):
    """Same AppTest/st.expander caveat as test_edit_meal_shows_success_message."""
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")
    meal_id = meals.list_all()[0].id
    ingredient_id = meals.list_ingredients(meal_id)[0][1].id

    at.tabs[0].number_input(key=f"edit_qty_{meal_id}_{ingredient_id}").set_value(500)
    at.run()
    at.tabs[0].button(key=f"save_ing_{meal_id}_{ingredient_id}").click().run()

    assert len(at.exception) == 0
    assert any("Ingredient updated" in s.value for s in at.success)
    assert any("Pasta — 500" in m.value for m in at.tabs[0].markdown)


def test_edit_ingredient_rejects_zero_quantity(meals):
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")
    meal_id = meals.list_all()[0].id
    ingredient_id = meals.list_ingredients(meal_id)[0][1].id

    at.tabs[0].number_input(key=f"edit_qty_{meal_id}_{ingredient_id}").set_value(0)
    at.run()
    at.tabs[0].button(key=f"save_ing_{meal_id}_{ingredient_id}").click().run()

    assert len(at.exception) == 0
    assert any("quantity greater than 0" in e.value for e in at.tabs[0].error)
    link, _ = meals.list_ingredients(meal_id)[0]
    assert link.qty == 200


# -------------------------------------------------------------- templates


def test_add_meal_from_template_creates_meal_and_ingredients(meals):
    at = run_app()
    template = MEAL_TEMPLATES[0]

    at.tabs[0].button(key=f"template_{template.name}").click().run()

    assert len(at.exception) == 0
    assert any(f"Added {template.name}" in s.value for s in at.success)

    saved = meals.list_all()
    assert [m.name for m in saved] == [template.name]
    attached = {i.name for _, i in meals.list_ingredients(saved[0].id)}
    assert attached == {item.name for item in template.ingredients}


def test_add_meal_from_template_twice_warns_instead_of_duplicating(meals):
    at = run_app()
    template = MEAL_TEMPLATES[0]

    at.tabs[0].button(key=f"template_{template.name}").click().run()
    at.tabs[0].button(key=f"template_{template.name}").click().run()

    assert len(at.exception) == 0
    assert any("already exists" in w.value for w in at.warning)
    assert len(meals.list_all()) == 1


# ------------------------------------------------------------ weekly plan


def test_unset_day_does_not_default_to_first_meal():
    """Regression test: day selectboxes used to default to the first meal,
    so submitting without touching every day silently overwrote them."""
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_meal(at, "Chicken Stir Fry")

    _plan_monday(at, "Spaghetti")

    assert len(at.exception) == 0
    assert ">—<" in _day_card(at, "Tue")


def test_copy_previous_week_plan_shows_success_and_copies_assignments():
    at = run_app()
    _add_meal(at, "Spaghetti")
    _plan_monday(at, "Spaghetti")

    current_monday = at.date_input(key="week_picker").value
    at.date_input(key="week_picker").set_value(current_monday + timedelta(days=7)).run()

    copy_key = [
        w.key for w in at.tabs[1].button if w.label == "Copy previous week's plan"
    ][0]
    at.tabs[1].button(key=copy_key).click().run()

    assert len(at.exception) == 0
    assert any("Copied last week's plan" in s.value for s in at.success)
    assert "Spaghetti" in _day_card(at, "Mon")


def test_copy_previous_week_with_no_source_reports_nothing_to_copy():
    at = run_app()
    _add_meal(at, "Spaghetti")

    copy_key = [
        w.key for w in at.tabs[1].button if w.label == "Copy previous week's plan"
    ][0]
    at.tabs[1].button(key=copy_key).click().run()

    assert len(at.exception) == 0
    assert any("No plan found" in i.value for i in at.tabs[1].info)


# ----------------------------------------------------------- grocery list


def test_planned_servings_scale_the_grocery_list():
    at = run_app()
    _add_meal(at, "Spaghetti", servings=4)
    _add_ingredient(at, "Spaghetti", "Pasta", 400, "g")

    _plan_monday(at, "Spaghetti", servings=2)
    assert "2 servings" in _day_card(at, "Mon")

    _generate_grocery_list(at)

    assert len(at.exception) == 0
    rows = [m.value for m in at.tabs[2].markdown if "grocery-row" in m.value]
    assert any("200 g" in row for row in rows)


def test_grocery_list_export_text_and_download_are_available():
    at = run_app()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")
    _plan_monday(at, "Spaghetti")

    _generate_grocery_list(at)

    assert len(at.exception) == 0
    text_areas = list(at.tabs[2].text_area)
    assert len(text_areas) == 1
    assert "- Pasta: 200 g" in text_areas[0].value
