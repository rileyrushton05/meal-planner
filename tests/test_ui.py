from datetime import timedelta

from streamlit.testing.v1 import AppTest

from app.crud import get_meals, get_meal_ingredients


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


def _add_ingredient(at, meal_name, ingredient_name, qty, unit):
    at.tabs[0].selectbox(key="ingredient_meal").select(meal_name).run()
    name_w = [w for w in at.tabs[0].text_input if w.label == "Ingredient name"][0]
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


def test_delete_meal_removes_it_from_list():
    at = AppTest.from_file("ui/streamlit_app.py")
    at.run()
    _add_meal(at, "Spaghetti")
    meal_id = get_meals()[0].id

    at.tabs[0].button(key=f"delete_meal_{meal_id}").click().run()

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
