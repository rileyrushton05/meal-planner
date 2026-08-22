from datetime import timedelta

from streamlit.testing.v1 import AppTest

from app.crud import get_meals, get_meal_ingredients
from app.templates import MEAL_TEMPLATES


def _submit_key(at, tab_index, form_name):
    return [
        w.key for w in at.tabs[tab_index].button
        if w.key and w.key.startswith(f"FormSubmitter:{form_name}")
    ][0]


def _add_meal(at, name, servings=None):
    at.tabs[0].text_input[0].input(name)
    if servings is not None:
        servings_widget = [w for w in at.tabs[0].number_input if w.label == "Servings"][0]
        servings_widget.set_value(servings)
    at.run()
    at.tabs[0].button(key=_submit_key(at, 0, "add_meal_form")).click().run()


def _seed_ingredient_searchbox(at, value):
    """AppTest has no way to drive the st_searchbox custom component's
    actual typing/selection interaction (it isn't part of AppTest's
    supported widget set). Instead this pre-seeds the component's own
    session_state entry with the value it would return after a
    selection - a white-box technique based on reading the library's
    source, verified to work, but it only covers the Python-side
    handling of the returned value, not the real search/render/select
    behavior in a browser."""
    generation = (
        at.session_state["ingredient_searchbox_generation"]
        if "ingredient_searchbox_generation" in at.session_state else 0
    )
    key = f"ingredient_searchbox_{generation}"
    at.session_state[key] = {
        "result": value,
        "search": value,
        "options_js": [],
        "options_py": [],
        "key_react": f"{key}_react_0",
    }


def _add_ingredient(at, meal_name, ingredient_name, qty, unit):
    """Adds an ingredient via the plain 'type a new one' text field -
    the guaranteed-reliable path, and the one most tests should use."""
    at.tabs[0].selectbox(key="ingredient_meal").select(meal_name).run()
    name_w = [w for w in at.tabs[0].text_input if w.label == "...or type a new one"][0]
    qty_w = [w for w in at.tabs[0].number_input if w.label == "Quantity"][0]
    unit_w = [w for w in at.tabs[0].text_input if w.label == "Unit (g, ml, tbsp...)"][0]
    name_w.input(ingredient_name)
    qty_w.set_value(qty)
    unit_w.input(unit)
    at.run()
    at.tabs[0].button(key="add_ingredient_btn").click().run()


def test_app_loads_with_three_tabs():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()

    assert len(at.exception) == 0
    assert len(at.tabs) == 3


def test_add_meal_shows_success_and_appears_in_list():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()

    _add_meal(at, "Spaghetti", servings=4)

    assert len(at.exception) == 0
    assert any("Added Spaghetti" in s.value for s in at.success)
    assert any("serves 4" in m.value for m in at.tabs[0].markdown)


def test_add_ingredient_shows_success_and_appears_in_list():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")

    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")

    assert len(at.exception) == 0
    assert any("Pasta added" in s.value for s in at.success)
    assert any("Pasta — 200.0 g" in m.value for m in at.tabs[0].markdown)


def test_add_ingredient_not_in_autocomplete_still_works():
    """Regression test: the ingredient name field used to be a single
    searchbox relying on typed-but-not-selected text being captured
    via default_use_searchterm. That could only be verified by faking
    the component's return value in a test, and turned out not to
    hold up in real use - typing something with no existing match
    (e.g. "Bread" on a fresh app) couldn't actually be added. Fixed
    by splitting into a searchbox for picking an existing ingredient
    and a separate plain text field for typing a new one; this test
    exercises the new-ingredient field specifically."""
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Sandwich")

    _add_ingredient(at, "Sandwich", "Bread", 4, "slices")

    assert len(at.exception) == 0
    assert any("Bread added" in s.value for s in at.success)
    assert any("Bread — 4.0 slices" in m.value for m in at.tabs[0].markdown)


def test_add_ingredient_via_searchbox_reuses_existing_ingredient():
    """Covers the other half of the ingredient field: picking an
    existing ingredient through the searchbox. Since AppTest can't
    drive the component's real search/select interaction, this seeds
    its session_state with the value a selection would produce (see
    _seed_ingredient_searchbox) - verifies the Python-side handling,
    not the actual browser interaction."""
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    _add_meal(at, "Garlic Bread")
    _add_ingredient(at, "Spaghetti", "Garlic", 2, "cloves")

    at.tabs[0].selectbox(key="ingredient_meal").select("Garlic Bread").run()
    _seed_ingredient_searchbox(at, "Garlic")
    qty_w = [w for w in at.tabs[0].number_input if w.label == "Quantity"][0]
    unit_w = [w for w in at.tabs[0].text_input if w.label == "Unit (g, ml, tbsp...)"][0]
    qty_w.set_value(1)
    unit_w.input("clove")
    at.run()
    at.tabs[0].button(key="add_ingredient_btn").click().run()

    assert len(at.exception) == 0
    assert any("Garlic added" in s.value for s in at.success)
    from app.crud import get_ingredients
    assert [i.name for i in get_ingredients()] == ["Garlic"]


def test_edit_meal_shows_success_message():
    """Verifies the edit-meal save flow shows a success message. Not a
    true regression test for the past swallowed-success-message bug -
    AppTest doesn't reproduce that failure for elements rendered
    inside st.expander (confirmed by manually reintroducing the bug:
    this test kept passing), unlike test_copy_previous_week_plan_*
    below, which does catch it."""
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    meal_id = get_meals()[0].id

    at.tabs[0].text_input(key=f"edit_name_{meal_id}").input("Spaghetti Bolognese")
    at.run()
    at.tabs[0].button(key=f"save_meal_{meal_id}").click().run()

    assert len(at.exception) == 0
    assert any("Meal updated" in s.value for s in at.success)
    assert any("Spaghetti Bolognese" in m.value for m in at.tabs[0].markdown)


def test_edit_ingredient_shows_success_message():
    """Verifies the edit-ingredient save flow shows a success message.
    Same AppTest/st.expander caveat as test_edit_meal_shows_success_message
    above - not a true regression test for the swallowed-message bug."""
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")
    meal_id = get_meals()[0].id
    ingredient_id = get_meal_ingredients(meal_id)[0][1].id

    at.tabs[0].number_input(key=f"edit_qty_{meal_id}_{ingredient_id}").set_value(500)
    at.run()
    at.tabs[0].button(key=f"save_ing_{meal_id}_{ingredient_id}").click().run()

    assert len(at.exception) == 0
    assert any("Ingredient updated" in s.value for s in at.success)
    assert any("Pasta — 500.0" in m.value for m in at.tabs[0].markdown)


def test_delete_meal_requires_confirmation():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    meal_id = get_meals()[0].id

    at.tabs[0].button(key=f"delete_meal_{meal_id}").click().run()
    assert get_meals() != []  # clicking Delete only asks for confirmation

    at.tabs[0].button(key=f"cancel_delete_{meal_id}").click().run()
    assert get_meals() != []  # Cancel must not delete

    at.tabs[0].button(key=f"delete_meal_{meal_id}").click().run()
    at.tabs[0].button(key=f"confirm_delete_{meal_id}").click().run()

    assert len(at.exception) == 0
    assert get_meals() == []


def test_unset_day_does_not_default_to_first_meal():
    """Regression test: day selectboxes used to default to the first
    meal alphabetically, so submitting without touching every day
    silently overwrote untouched days with that meal."""
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    _add_meal(at, "Chicken Stir Fry")

    monday_key = [w.key for w in at.tabs[1].selectbox if w.key and w.key.endswith("_Monday")][0]
    at.tabs[1].selectbox(key=monday_key).select("Spaghetti")
    at.run()
    at.tabs[1].button(key=_submit_key(at, 1, "weekly_plan_form")).click().run()

    assert len(at.exception) == 0
    day_cards = [m.value for m in at.tabs[1].markdown if "day-card" in m.value]
    tuesday_card = [c for c in day_cards if "Tue" in c][0]
    assert ">—<" in tuesday_card


def test_copy_previous_week_plan_shows_success_and_copies_assignments():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")

    monday_key = [w.key for w in at.tabs[1].selectbox if w.key and w.key.endswith("_Monday")][0]
    at.tabs[1].selectbox(key=monday_key).select("Spaghetti")
    at.run()
    at.tabs[1].button(key=_submit_key(at, 1, "weekly_plan_form")).click().run()

    current_monday = at.date_input(key="week_picker").value
    at.date_input(key="week_picker").set_value(current_monday + timedelta(days=7)).run()

    copy_key = [w.key for w in at.tabs[1].button if w.label == "Copy previous week's plan"][0]
    at.tabs[1].button(key=copy_key).click().run()

    assert len(at.exception) == 0
    assert any("Copied last week's plan" in s.value for s in at.success)
    day_cards = [m.value for m in at.tabs[1].markdown if "day-card" in m.value]
    monday_card = [c for c in day_cards if "Mon" in c][0]
    assert "Spaghetti" in monday_card


def test_planned_servings_scale_the_grocery_list():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti", servings=4)
    _add_ingredient(at, "Spaghetti", "Pasta", 400, "g")

    monday_key = [w.key for w in at.tabs[1].selectbox if w.key and w.key.endswith("_Monday")][0]
    servings_key = [
        w.key for w in at.tabs[1].number_input
        if w.key and w.key.endswith("_Monday") and "servings" in w.key
    ][0]
    at.tabs[1].selectbox(key=monday_key).select("Spaghetti")
    at.tabs[1].number_input(key=servings_key).set_value(2)
    at.run()
    at.tabs[1].button(key=_submit_key(at, 1, "weekly_plan_form")).click().run()

    day_cards = [m.value for m in at.tabs[1].markdown if "day-card" in m.value]
    monday_card = [c for c in day_cards if "Mon" in c][0]
    assert "2 servings" in monday_card

    at.tabs[2].button(key=[w.key for w in at.tabs[2].button][0]).click().run()

    assert len(at.exception) == 0
    assert any("200.0 g" in m.value for m in at.tabs[2].markdown if "grocery-row" in m.value)


def test_grocery_list_export_text_and_download_are_available():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    _add_ingredient(at, "Spaghetti", "Pasta", 200, "g")

    monday_key = [w.key for w in at.tabs[1].selectbox if w.key and w.key.endswith("_Monday")][0]
    at.tabs[1].selectbox(key=monday_key).select("Spaghetti")
    at.run()
    at.tabs[1].button(key=_submit_key(at, 1, "weekly_plan_form")).click().run()

    at.tabs[2].button(key=[w.key for w in at.tabs[2].button][0]).click().run()

    assert len(at.exception) == 0
    text_areas = list(at.tabs[2].text_area)
    assert len(text_areas) == 1
    assert "- Pasta: 200.0 g" in text_areas[0].value


def test_add_meal_from_template_creates_meal_and_ingredients():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()

    template = MEAL_TEMPLATES[0]
    at.tabs[0].button(key=f"template_{template['name']}").click().run()

    assert len(at.exception) == 0
    assert any(f"Added {template['name']}" in s.value for s in at.success)

    meals = get_meals()
    assert [m.name for m in meals] == [template["name"]]
    saved_ingredients = {i.name for _, i in get_meal_ingredients(meals[0].id)}
    assert saved_ingredients == {name for name, _, _ in template["ingredients"]}


def test_add_meal_from_template_twice_warns_instead_of_duplicating():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()

    template = MEAL_TEMPLATES[0]
    at.tabs[0].button(key=f"template_{template['name']}").click().run()
    at.tabs[0].button(key=f"template_{template['name']}").click().run()

    assert len(at.exception) == 0
    assert any("already exists" in w.value for w in at.warning)
    assert len(get_meals()) == 1
