import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.crud import (
    add_meal,
    get_meals,
    set_meal_for_day,
    add_ingredient_to_meal,
    get_weekly_plan,
    delete_meal,
    get_meal_ingredients,
    remove_ingredient_from_meal,
    update_meal,
    update_meal_ingredient,
)
from app.db import create_db_and_tables
from app.planner import generate_weekly_grocery_list

create_db_and_tables()

st.set_page_config(page_title="Weekly Meal Planner", layout="wide")

BG_COLOR = "#14151D"
SURFACE = "#1C1E27"
BORDER = "#2B2E3A"
TEXT_COLOR = "#E5E7EB"
TEXT_MUTED = "#9CA3AF"
ACCENT_COLOR = "#818CF8"
ACCENT_HOVER = "#6366F1"
ACCENT_CONTRAST = "#14151D"

DAY_COLORS = {
    "Monday": "#6366F1",
    "Tuesday": "#0D9488",
    "Wednesday": "#D97706",
    "Thursday": "#2563EB",
    "Friday": "#DB2777",
    "Saturday": "#16A34A",
    "Sunday": "#7C3AED",
}
DAYS = list(DAY_COLORS.keys())

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Manrope:wght@400;500;600;700&display=swap');

    /* Force the app's look regardless of whether .streamlit/config.toml
       was discovered - its lookup depends on the launching process's
       working directory, which differs between a terminal and some
       IDE run buttons, so config.toml alone isn't reliable. */
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"] {{
        background-color: {BG_COLOR} !important;
        color: {TEXT_COLOR} !important;
    }}

    html, body, [class*="css"] {{
        font-family: 'Manrope', system-ui, sans-serif;
    }}

    /* Every button is indigo by default - simpler and more reliable
       than matching Streamlit's kind="primary" attribute, which turns
       out to differ for form-submit buttons vs plain buttons across
       versions. The muted look for Delete/Remove is then carved back
       out below using kind="secondary", which we've confirmed does
       match consistently. */
    [data-testid="stAppViewContainer"] .stButton button,
    [data-testid="stAppViewContainer"] .stFormSubmitButton button {{
        background-color: {ACCENT_COLOR} !important;
        border-color: {ACCENT_COLOR} !important;
        color: {ACCENT_CONTRAST} !important;
    }}
    [data-testid="stAppViewContainer"] .stButton button p,
    [data-testid="stAppViewContainer"] .stFormSubmitButton button p {{
        color: {ACCENT_CONTRAST} !important;
    }}
    [data-testid="stAppViewContainer"] .stButton button:hover,
    [data-testid="stAppViewContainer"] .stFormSubmitButton button:hover {{
        background-color: {ACCENT_HOVER} !important;
        border-color: {ACCENT_HOVER} !important;
    }}
    [data-testid="stAppViewContainer"] .stButton button:hover p,
    [data-testid="stAppViewContainer"] .stFormSubmitButton button:hover p {{
        color: #FFFFFF !important;
    }}

    [data-testid="stAppViewContainer"] button[kind="secondary"] {{
        background-color: {SURFACE} !important;
        border: 1px solid {BORDER} !important;
        color: {TEXT_MUTED} !important;
    }}
    [data-testid="stAppViewContainer"] button[kind="secondary"] p {{
        color: {TEXT_MUTED} !important;
    }}
    [data-testid="stAppViewContainer"] button[kind="secondary"]:hover {{
        background-color: {BORDER} !important;
        border-color: {TEXT_MUTED} !important;
        color: {TEXT_COLOR} !important;
    }}

    [data-baseweb="tab-highlight"] {{
        background-color: {ACCENT_COLOR} !important;
    }}
    .stTabs button[aria-selected="true"] p {{
        color: {ACCENT_COLOR} !important;
    }}

    h1 {{
        font-family: 'Sora', system-ui, sans-serif;
        font-weight: 700;
        font-size: 2.1rem;
        letter-spacing: -0.01em;
        color: {TEXT_COLOR};
    }}
    h3 {{
        font-family: 'Sora', system-ui, sans-serif;
        font-weight: 700;
        font-size: 1.15rem;
        color: {TEXT_COLOR};
    }}

    [data-testid="stCaptionContainer"] {{
        color: {TEXT_MUTED} !important;
    }}

    .stTabs [data-baseweb="tab-list"] button {{
        font-family: 'Sora', system-ui, sans-serif;
        font-weight: 600;
        font-size: 0.95rem;
    }}
    .stTabs [data-baseweb="tab-list"] button p {{
        color: {TEXT_MUTED} !important;
    }}
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] p {{
        color: {ACCENT_COLOR} !important;
    }}

    div.stButton > button, div.stFormSubmitButton > button {{
        font-family: 'Manrope', system-ui, sans-serif;
        font-weight: 700;
        font-size: 0.88rem;
        border-radius: 8px;
        padding: 0.6rem 1.15rem;
    }}
    button[kind="secondary"] {{
        color: {TEXT_MUTED};
    }}

    [data-testid="stWidgetLabel"] p {{
        font-family: 'Manrope', system-ui, sans-serif;
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: {TEXT_MUTED};
    }}

    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {{
        font-family: 'Manrope', system-ui, sans-serif;
        font-size: 0.92rem;
        border-radius: 8px !important;
    }}

    /* Input/select fill and text color, forced explicitly - these
       otherwise default to whatever base (light/dark) theme Streamlit
       computed internally, independent of the page background we
       force above, producing a mismatched dark-box-on-white-page look. */
    [data-testid="stTextInput"] div[data-baseweb="base-input"],
    [data-testid="stNumberInput"] div[data-baseweb="base-input"],
    .stSelectbox div[data-baseweb="select"] > div {{
        background-color: {SURFACE} !important;
        border-color: {BORDER} !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    .stSelectbox div[data-baseweb="select"] * {{
        color: {TEXT_COLOR} !important;
        background-color: transparent !important;
    }}

    /* The select dropdown menu is portalled outside stAppViewContainer,
       so it needs its own unscoped rule. */
    [data-baseweb="popover"] [data-baseweb="menu"] {{
        background-color: {SURFACE} !important;
    }}
    [data-baseweb="popover"] [data-baseweb="menu"] li {{
        color: {TEXT_COLOR} !important;
    }}

    [data-testid="stForm"] {{
        border-radius: 10px;
        padding: 1.25rem;
        background-color: {SURFACE};
        border: 1px solid {BORDER};
    }}

    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 10px !important;
        background-color: {SURFACE};
        border: 1px solid {BORDER} !important;
    }}

    hr {{
        border-color: {BORDER} !important;
        margin: 2rem 0 !important;
    }}

    .day-card {{
        border-radius: 10px;
        padding: 0.95rem 0.6rem;
        text-align: center;
        color: #FFFFFF;
    }}
    .day-card .day-name {{
        font-family: 'Manrope', system-ui, sans-serif;
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        opacity: 0.85;
    }}
    .day-card .meal-name {{
        font-family: 'Sora', system-ui, sans-serif;
        font-weight: 600;
        font-size: 0.88rem;
        margin-top: 0.4rem;
        line-height: 1.25;
    }}

    .grocery-row {{
        border-radius: 10px;
        padding: 0.75rem 1.1rem;
        margin-bottom: 0.6rem;
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        display: flex;
        justify-content: space-between;
        align-items: center;
        color: {TEXT_COLOR};
        font-family: 'Manrope', system-ui, sans-serif;
    }}
    .grocery-row .qty {{
        font-variant-numeric: tabular-nums;
        font-weight: 700;
        font-size: 0.9rem;
        color: {ACCENT_COLOR};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Weekly Meal Planner")
st.caption("Plan your meals, build your week, and generate your grocery list — all in one place.")

today = date.today()
default_monday = today - timedelta(days=today.weekday())
picked_date = st.date_input("Week", value=default_monday, key="week_picker")
selected_monday = picked_date - timedelta(days=picked_date.weekday())
selected_sunday = selected_monday + timedelta(days=6)
st.caption(
    f"Viewing week of {selected_monday.strftime('%b %d')} – {selected_sunday.strftime('%b %d, %Y')}"
)

tab_meals, tab_plan, tab_grocery = st.tabs(["Meals", "Weekly Plan", "Grocery List"])

# ---------------------------------------------------------------- Meals tab
with tab_meals:
    st.subheader("Add a Meal")
    with st.form("add_meal_form", clear_on_submit=True):
        col_name, col_servings = st.columns([4, 1])
        with col_name:
            meal_name = st.text_input("Meal name")
        with col_servings:
            servings = st.number_input("Servings", min_value=1, step=1, value=1)
        submitted_meal = st.form_submit_button("Add Meal", type="primary")
        if submitted_meal:
            if meal_name.strip():
                try:
                    add_meal(meal_name.strip(), servings=int(servings))
                    st.success(f"Added {meal_name.strip()}!")
                except ValueError as e:
                    st.error(str(e))
            else:
                st.error("Please enter a meal name.")

    st.subheader("Your Meals")
    existing_meals = get_meals()
    if existing_meals:
        for meal in existing_meals:
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"**{meal.name}**  \n:gray[serves {meal.servings}]")
                if c2.button("Delete", key=f"delete_meal_{meal.id}", help=f"Delete {meal.name}"):
                    delete_meal(meal.id)
                    st.rerun()

                with st.expander("Edit"):
                    edit_col_name, edit_col_servings = st.columns([4, 1])
                    with edit_col_name:
                        edited_name = st.text_input(
                            "Meal name", value=meal.name, key=f"edit_name_{meal.id}"
                        )
                    with edit_col_servings:
                        edited_servings = st.number_input(
                            "Servings", min_value=1, step=1, value=meal.servings,
                            key=f"edit_servings_{meal.id}"
                        )
                    if st.button("Save", key=f"save_meal_{meal.id}"):
                        if edited_name.strip():
                            try:
                                update_meal(meal.id, edited_name.strip(), int(edited_servings))
                                st.session_state[f"meal_updated_{meal.id}"] = True
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                        else:
                            st.error("Please enter a meal name.")

                    if st.session_state.pop(f"meal_updated_{meal.id}", False):
                        st.success("Meal updated!")
    else:
        st.info("No meals yet — add your first one above!")

    st.divider()
    st.subheader("Add Ingredients to a Meal")

    if existing_meals:
        meal_names = {meal.name: meal.id for meal in existing_meals}
        selected_meal = st.selectbox("Select Meal", list(meal_names.keys()), key="ingredient_meal")
        meal_id = meal_names[selected_meal]

        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_a:
            ingredient_name = st.text_input("Ingredient name")
        with col_b:
            qty = st.number_input("Quantity", min_value=0.0, step=1.0)
        with col_c:
            unit = st.text_input("Unit (g, ml, tbsp...)")

        if st.button("Add Ingredient", key="add_ingredient_btn", type="primary"):
            if not ingredient_name.strip():
                st.error("Please enter an ingredient name.")
            else:
                try:
                    add_ingredient_to_meal(meal_id, ingredient_name.strip(), qty, unit)
                    st.success(f"{ingredient_name} added to {selected_meal}")
                except ValueError as e:
                    st.error(str(e))

        current_ingredients = get_meal_ingredients(meal_id)
        if current_ingredients:
            st.markdown(f"**Ingredients in {selected_meal}:**")
            for link, ingredient in current_ingredients:
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    c1.write(f"{ingredient.name} — {link.qty or 0} {link.unit or ''}".strip())
                    if c2.button("Remove", key=f"remove_ing_{meal_id}_{ingredient.id}"):
                        remove_ingredient_from_meal(meal_id, ingredient.id)
                        st.rerun()

                    with st.expander("Edit"):
                        edit_col_qty, edit_col_unit = st.columns(2)
                        with edit_col_qty:
                            edited_qty = st.number_input(
                                "Quantity", min_value=0.0, step=1.0,
                                value=float(link.qty or 0),
                                key=f"edit_qty_{meal_id}_{ingredient.id}"
                            )
                        with edit_col_unit:
                            edited_unit = st.text_input(
                                "Unit", value=link.unit or "",
                                key=f"edit_unit_{meal_id}_{ingredient.id}"
                            )
                        if st.button("Save", key=f"save_ing_{meal_id}_{ingredient.id}"):
                            update_meal_ingredient(meal_id, ingredient.id, edited_qty, edited_unit.strip())
                            st.session_state[f"ing_updated_{meal_id}_{ingredient.id}"] = True
                            st.rerun()

                        if st.session_state.pop(f"ing_updated_{meal_id}_{ingredient.id}", False):
                            st.success("Ingredient updated!")
        else:
            st.caption("No ingredients added yet.")
    else:
        st.caption("Add a meal first to attach ingredients to it.")

# ------------------------------------------------------------ Weekly Plan tab
with tab_plan:
    st.subheader("Assign Meals to Days")

    meals = get_meals()
    meal_names = {meal.name: meal.id for meal in meals}

    if meal_names:
        previous_monday = selected_monday - timedelta(days=7)
        if st.button("Copy previous week's plan"):
            previous_plans = get_weekly_plan(previous_monday)
            if previous_plans:
                for p in previous_plans:
                    if p.meal_id:
                        set_meal_for_day(selected_monday, p.day_of_week, p.meal_id)
                st.session_state["copy_plan_success"] = True
                st.rerun()
            else:
                st.info(f"No plan found for the week of {previous_monday.strftime('%b %d, %Y')}.")

        if st.session_state.pop("copy_plan_success", False):
            st.success("Copied last week's plan!")

        UNSET = "— Unset —"
        existing_plans = get_weekly_plan(selected_monday)
        existing_by_day = {p.day_of_week: p.meal_id for p in existing_plans}
        meal_id_to_name = {meal.id: meal.name for meal in meals}

        with st.form("weekly_plan_form"):
            day_to_meal = {}
            meal_option_list = [UNSET] + list(meal_names.keys())
            for day in DAYS:
                current_name = meal_id_to_name.get(existing_by_day.get(day))
                default_index = (
                    meal_option_list.index(current_name)
                    if current_name in meal_option_list else 0
                )
                selected = st.selectbox(
                    day, meal_option_list, index=default_index,
                    key=f"plan_{selected_monday}_{day}"
                )
                day_to_meal[day] = selected

            submitted = st.form_submit_button("Set Weekly Plan", type="primary")
            if submitted:
                for day, meal_name in day_to_meal.items():
                    meal_id = meal_names.get(meal_name)
                    set_meal_for_day(selected_monday, day, meal_id)
                st.success("Weekly plan saved!")
    else:
        st.info("Add a meal first before assigning it to days.")

    st.divider()
    st.subheader(f"Week of {selected_monday.strftime('%b %d, %Y')}")

    plans = get_weekly_plan(selected_monday)
    if plans:
        meal_lookup = {meal.id: meal.name for meal in get_meals()}
        plan_lookup = {p.day_of_week: p.meal_id for p in plans}

        cols = st.columns(7)
        for col, day in zip(cols, DAYS):
            meal_for_day = meal_lookup.get(plan_lookup.get(day), "—")
            color = DAY_COLORS[day]
            col.markdown(
                f"""
                <div class="day-card" style="background-color:{color};">
                    <div class="day-name">{day[:3]}</div>
                    <div class="meal-name">{meal_for_day}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No meals assigned yet.")

# ------------------------------------------------------------- Grocery tab
with tab_grocery:
    st.subheader(f"Grocery List — Week of {selected_monday.strftime('%b %d, %Y')}")

    grocery_key = f"grocery_list_{selected_monday}"
    if st.button("Generate Grocery List", type="primary"):
        st.session_state[grocery_key] = generate_weekly_grocery_list(selected_monday)

    grocery = st.session_state.get(grocery_key)
    if grocery:
        for ingredient, amount in grocery.items():
            st.markdown(
                f"""
                <div class="grocery-row">
                    <span>{ingredient}</span>
                    <span class="qty">{amount}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    elif grocery is not None:
        st.info("No meals assigned this week yet!")
