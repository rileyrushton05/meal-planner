import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st
import pandas as pd
from app.crud import add_meal, get_meals, set_meal_for_day
from app.db import create_db_and_tables
from app.planner import generate_weekly_grocery_list

# Create tables if they don't exist
create_db_and_tables()

st.title("Weekly Meal Planner")

# Add Meal Section 
st.header("Add Meal")
meal_name = st.text_input("Meal name")

if st.button("Add Meal"):
    add_meal(meal_name)
    st.success("Meal added!")


# Assign Meals to Days Section
st.header("Assign Meals to Days")

meals = get_meals()
meal_names = {meal.name: meal.id for meal in meals}
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

with st.form("weekly_plan_form"):
    day_to_meal = {}
    for day in days:
        selected = st.selectbox(day, list(meal_names.keys()), key=day)
        day_to_meal[day] = selected

    submitted = st.form_submit_button("Set Weekly Plan")
    if submitted:
        for day, meal_name in day_to_meal.items():
            set_meal_for_day(day, meal_names[meal_name])
        st.success("Weekly plan saved!")


# Weekly Grocery List Section 
st.header("Weekly Grocery List")

if st.button("Generate Grocery List"):
    grocery = generate_weekly_grocery_list()
    if grocery:
        df = pd.DataFrame([
            {"Ingredient": k, "Quantity": v}
            for k, v in grocery.items()
        ])
        st.table(df)
    else:
        st.info("No meals assigned this week yet!")