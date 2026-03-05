import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
from app.crud import add_meal, get_meals, set_meal_for_day
from app.db import create_db_and_tables

create_db_and_tables()

st.title("Weekly Meal Planner")

st.header("Add Meal")

meal_name = st.text_input("Meal name")

if st.button("Add Meal"):
    add_meal(meal_name)
    st.success("Meal added!")

st.header("Assign Meals to Days")

meals = get_meals()

meal_names = {meal.name: meal.id for meal in meals}

days = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

for day in days:

    selected_meal = st.selectbox(
        f"{day}",
        list(meal_names.keys()),
        key=day
    )

    if st.button(f"Set {day}"):

        meal_id = meal_names[selected_meal]

        set_meal_for_day(day, meal_id)

        st.success(f"{selected_meal} set for {day}")