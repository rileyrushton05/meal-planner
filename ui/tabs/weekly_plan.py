"""Weekly Plan tab: assign a meal and serving count to each day."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from app.models import DayOfWeek, Meal, WeeklyPlan
from ui.services import Services
from ui.styles import DAY_COLORS

#: Selectbox entry meaning "no meal for this day". Chosen over defaulting to
#: the first meal, which silently overwrote days the user never touched.
UNSET_LABEL = "— Unset —"


def render(services: Services, week_start: date) -> None:
    """Draw the whole Weekly Plan tab for the given week."""
    st.subheader("Assign Meals to Days")

    meals = services.meals.list_all()
    # Fetched once and passed down. The form and the overview below both
    # need it, and a second call would be another network round trip on
    # every single interaction.
    plans = services.plans.get_week(week_start)

    if meals:
        _render_copy_previous_week(services, week_start)
        _render_plan_form(services, week_start, meals, plans)
        if st.session_state.pop("plan_saved", False):
            st.success("Weekly plan saved!")
    else:
        st.info("Add a meal first before assigning it to days.")

    st.divider()
    st.subheader(f"Week of {week_start.strftime('%b %d, %Y')}")
    _render_week_overview(week_start, meals, plans)


def _render_copy_previous_week(services: Services, week_start: date) -> None:
    previous_week = week_start - timedelta(days=7)

    if st.button("Copy previous week's plan"):
        copied = services.plans.copy_week(previous_week, week_start)
        if copied:
            st.session_state["copy_plan_success"] = True
            st.rerun()
        else:
            st.info(
                f"No plan found for the week of {previous_week.strftime('%b %d, %Y')}."
            )

    if st.session_state.pop("copy_plan_success", False):
        st.success("Copied last week's plan!")


def _render_plan_form(
    services: Services,
    week_start: date,
    meals: list[Meal],
    plans: list[WeeklyPlan],
) -> None:
    meal_ids_by_name = {meal.name: meal.id for meal in meals}
    names_by_meal_id = {meal.id: meal.name for meal in meals}
    base_servings_by_meal_id = {meal.id: meal.servings for meal in meals}

    existing = {plan.day_of_week: plan for plan in plans}
    options = [UNSET_LABEL, *meal_ids_by_name]

    with st.form("weekly_plan_form"):
        chosen: dict[DayOfWeek, tuple[str, int]] = {}

        for day in DayOfWeek:
            plan = existing.get(str(day))
            current_name = names_by_meal_id.get(plan.meal_id) if plan else None
            default_servings = (
                (plan.servings if plan else None)
                or base_servings_by_meal_id.get(plan.meal_id if plan else None)
                or 1
            )

            col_meal, col_servings = st.columns([3, 1])
            with col_meal:
                selected = st.selectbox(
                    str(day),
                    options,
                    index=options.index(current_name) if current_name in options else 0,
                    key=f"plan_{week_start}_{day}",
                )
            with col_servings:
                servings = st.number_input(
                    "Servings",
                    min_value=1,
                    step=1,
                    value=int(default_servings),
                    key=f"plan_servings_{week_start}_{day}",
                )
            chosen[day] = (selected, int(servings))

        if st.form_submit_button("Set Weekly Plan", type="primary"):
            for day, (meal_name, servings) in chosen.items():
                meal_id = meal_ids_by_name.get(meal_name)
                services.plans.set_day(
                    week_start, day, meal_id, servings if meal_id else None
                )
            # Rerun so the week overview re-reads what was just written. The
            # plan list is loaded once at the top of the tab and shared, so
            # without this it would still hold pre-save data. The message is
            # deferred because st.rerun() discards anything already emitted.
            st.session_state["plan_saved"] = True
            st.rerun()


def _render_week_overview(
    week_start: date, meals: list[Meal], plans: list[WeeklyPlan]
) -> None:
    if not plans:
        st.info("No meals assigned yet.")
        return

    names_by_meal_id = {meal.id: meal.name for meal in meals}
    plans_by_day = {plan.day_of_week: plan for plan in plans}

    for column, day in zip(st.columns(len(DayOfWeek)), DayOfWeek):
        plan = plans_by_day.get(str(day))
        meal_name = names_by_meal_id.get(plan.meal_id, "—") if plan else "—"
        column.markdown(
            _day_card_html(day, meal_name, plan.servings if plan else None),
            unsafe_allow_html=True,
        )


def _day_card_html(day: DayOfWeek, meal_name: str, servings: int | None) -> str:
    detail = ""
    if meal_name != "—" and servings:
        detail = f"{servings} serving{'s' if servings != 1 else ''}"
    return f"""
        <div class="day-card" style="background-color:{DAY_COLORS[day]};">
            <div class="day-name">{day.short_name}</div>
            <div class="meal-name">{meal_name}</div>
            <div class="day-name">{detail}</div>
        </div>
    """
