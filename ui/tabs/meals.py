"""Meals tab: create, edit and delete meals and their ingredients."""

from __future__ import annotations

import streamlit as st
from streamlit_searchbox import st_searchbox

from app.exceptions import MealPlannerError
from app.models import Ingredient, Meal, MealIngredient
from app.templates import MEAL_TEMPLATES, MealTemplate
from app.units import format_qty
from ui.services import Services

#: Bumped after each successful add to give the ingredient inputs fresh
#: keys, which is how a custom component gets cleared between entries.
_SEARCHBOX_GENERATION = "ingredient_searchbox_generation"


def render(services: Services) -> None:
    """Draw the whole Meals tab."""
    _render_add_meal_form(services)
    _render_template_gallery(services)

    st.subheader("Your Meals")
    meals = services.meals.list_all()
    if not meals:
        st.info("No meals yet — add your first one above!")
    else:
        for meal in meals:
            _render_meal_card(services, meal)

    st.divider()
    st.subheader("Add Ingredients to a Meal")
    if meals:
        _render_ingredient_editor(services, meals)
    else:
        st.caption("Add a meal first to attach ingredients to it.")


# ------------------------------------------------------------ adding meals


def _render_add_meal_form(services: Services) -> None:
    st.subheader("Add a Meal")
    with st.form("add_meal_form", clear_on_submit=True):
        col_name, col_servings = st.columns([4, 1])
        with col_name:
            name = st.text_input("Meal name")
        with col_servings:
            servings = st.number_input("Servings", min_value=1, step=1, value=1)

        if not st.form_submit_button("Add Meal", type="primary"):
            return

        if not name.strip():
            st.error("Please enter a meal name.")
            return
        try:
            services.meals.add(name.strip(), servings=int(servings))
            st.success(f"Added {name.strip()}!")
        except MealPlannerError as exc:
            st.error(str(exc))


def _render_template_gallery(services: Services) -> None:
    with st.expander("Quick Add from Templates"):
        st.caption("One-click starter meals with typical ingredients already filled in.")
        columns = st.columns(3)
        for index, template in enumerate(MEAL_TEMPLATES):
            with columns[index % 3]:
                _render_template_card(services, template)

        if "template_added_message" in st.session_state:
            st.success(st.session_state.pop("template_added_message"))


def _render_template_card(services: Services, template: MealTemplate) -> None:
    with st.container(border=True):
        st.markdown(f"**{template.name}**  \n:gray[serves {template.servings}]")
        st.caption(template.ingredient_summary)
        if not st.button("Add", key=f"template_{template.name}"):
            return
        try:
            services.meals.add_from_template(template)
            st.session_state["template_added_message"] = f"Added {template.name}!"
            st.rerun()
        except MealPlannerError as exc:
            st.warning(str(exc))


# ----------------------------------------------------- editing/deleting


def _render_meal_card(services: Services, meal: Meal) -> None:
    with st.container(border=True):
        summary, action = st.columns([5, 1])
        summary.markdown(f"**{meal.name}**  \n:gray[serves {meal.servings}]")
        _render_delete_controls(services, meal, action)
        _render_edit_form(services, meal)


def _render_delete_controls(services: Services, meal: Meal, action_column) -> None:
    """Two-step delete, since deleting also drops ingredients and plan days."""
    pending_key = f"pending_delete_{meal.id}"

    if not st.session_state.get(pending_key):
        if action_column.button(
            "Delete", key=f"delete_meal_{meal.id}", help=f"Delete {meal.name}"
        ):
            st.session_state[pending_key] = True
            st.rerun()
        return

    st.warning(
        f"Delete **{meal.name}**? This also removes its ingredients "
        f"and unassigns it from any day it's currently planned on."
    )
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", key=f"cancel_delete_{meal.id}"):
        st.session_state[pending_key] = False
        st.rerun()
    if confirm.button("Yes, delete", key=f"confirm_delete_{meal.id}", type="primary"):
        services.meals.delete(meal.id)
        st.session_state.pop(pending_key, None)
        st.rerun()


def _render_edit_form(services: Services, meal: Meal) -> None:
    with st.expander("Edit"):
        col_name, col_servings = st.columns([4, 1])
        with col_name:
            name = st.text_input(
                "Meal name", value=meal.name, key=f"edit_name_{meal.id}"
            )
        with col_servings:
            servings = st.number_input(
                "Servings",
                min_value=1,
                step=1,
                value=meal.servings,
                key=f"edit_servings_{meal.id}",
            )

        if st.button("Save", key=f"save_meal_{meal.id}"):
            if not name.strip():
                st.error("Please enter a meal name.")
            else:
                try:
                    services.meals.update(meal.id, name.strip(), int(servings))
                    # Deferred to the next run: st.rerun() discards anything
                    # already written this run, including a success message.
                    st.session_state[f"meal_updated_{meal.id}"] = True
                    st.rerun()
                except MealPlannerError as exc:
                    st.error(str(exc))

        if st.session_state.pop(f"meal_updated_{meal.id}", False):
            st.success("Meal updated!")


# ------------------------------------------------------------- ingredients


def _render_ingredient_editor(services: Services, meals: list[Meal]) -> None:
    meal_ids_by_name = {meal.name: meal.id for meal in meals}
    selected_name = st.selectbox(
        "Select Meal", list(meal_ids_by_name), key="ingredient_meal"
    )
    meal_id = meal_ids_by_name[selected_name]

    _render_add_ingredient_form(services, meal_id, selected_name)

    attached = services.meals.list_ingredients(meal_id)
    if not attached:
        st.caption("No ingredients added yet.")
        return

    st.markdown(f"**Ingredients in {selected_name}:**")
    for link, ingredient in attached:
        _render_ingredient_row(services, meal_id, link, ingredient)


def _render_add_ingredient_form(
    services: Services, meal_id: int, meal_name: str
) -> None:
    """Ingredient entry: pick a known one, or type a brand new one.

    Two separate inputs rather than one combobox. Relying on the searchbox
    to also return free text meant an ingredient with no existing match
    couldn't be added at all.
    """
    st.session_state.setdefault(_SEARCHBOX_GENERATION, 0)
    generation = st.session_state[_SEARCHBOX_GENERATION]

    col_name, col_qty, col_unit = st.columns([2, 1, 1])
    with col_name:
        picked = st_searchbox(
            services.ingredients.search_names,
            placeholder="Pick an existing ingredient...",
            label="Existing ingredient",
            default="",
            key=f"ingredient_searchbox_{generation}",
        )
        typed = st.text_input(
            "...or type a new one", key=f"new_ingredient_name_{generation}"
        )
        name = typed.strip() or (picked or "").strip()
    with col_qty:
        qty = st.number_input("Quantity", min_value=0.0, step=1.0)
    with col_unit:
        unit = st.text_input("Unit (g, ml, tbsp...)")

    if st.button("Add Ingredient", key="add_ingredient_btn", type="primary"):
        if not name:
            st.error("Please enter an ingredient name.")
        elif qty <= 0:
            st.error("Please enter a quantity greater than 0.")
        else:
            try:
                services.meals.add_ingredient(meal_id, name, qty, unit)
                st.session_state["ingredient_added_message"] = (
                    f"{name} added to {meal_name}"
                )
                st.session_state[_SEARCHBOX_GENERATION] += 1
                st.rerun()
            except MealPlannerError as exc:
                st.error(str(exc))

    if "ingredient_added_message" in st.session_state:
        st.success(st.session_state.pop("ingredient_added_message"))


def _render_ingredient_row(
    services: Services, meal_id: int, link: MealIngredient, ingredient: Ingredient
) -> None:
    with st.container(border=True):
        summary, action = st.columns([5, 1])
        amount = f"{format_qty(link.qty or 0)} {link.unit or ''}".strip()
        summary.write(f"{ingredient.name} — {amount}")

        if action.button("Remove", key=f"remove_ing_{meal_id}_{ingredient.id}"):
            services.meals.remove_ingredient(meal_id, ingredient.id)
            st.rerun()

        with st.expander("Edit"):
            col_qty, col_unit = st.columns(2)
            with col_qty:
                qty = st.number_input(
                    "Quantity",
                    min_value=0.0,
                    step=1.0,
                    value=float(link.qty or 0),
                    key=f"edit_qty_{meal_id}_{ingredient.id}",
                )
            with col_unit:
                unit = st.text_input(
                    "Unit",
                    value=link.unit or "",
                    key=f"edit_unit_{meal_id}_{ingredient.id}",
                )

            updated_key = f"ing_updated_{meal_id}_{ingredient.id}"
            if st.button("Save", key=f"save_ing_{meal_id}_{ingredient.id}"):
                if qty <= 0:
                    st.error("Please enter a quantity greater than 0.")
                else:
                    services.meals.update_ingredient(
                        meal_id, ingredient.id, qty, unit.strip()
                    )
                    st.session_state[updated_key] = True
                    st.rerun()

            if st.session_state.pop(updated_key, False):
                st.success("Ingredient updated!")
