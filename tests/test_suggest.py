"""Suggesting meals for empty days (app/suggest.py)."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import DayOfWeek
from app.suggest import day_date, suggest_for_empty_days

MON, TUE, WED, THU, FRI, SAT, SUN = list(DayOfWeek)
WEEK = date(2026, 11, 16)  # a Monday


def weeks_ago(n: int, day: DayOfWeek = MON) -> date:
    return day_date(WEEK - timedelta(weeks=n), day)


def suggest(empty, meal_ids, planned=(), this_week=()):
    return suggest_for_empty_days(
        week_start=WEEK,
        empty=empty,
        meal_ids=meal_ids,
        planned=planned,
        already_this_week=this_week,
    )


def test_the_meal_cooked_longest_ago_comes_first() -> None:
    planned = [(1, weeks_ago(1)), (2, weeks_ago(6)), (3, weeks_ago(3))]

    assert suggest([MON, TUE, WED], [1, 2, 3], planned) == {MON: 2, TUE: 3, WED: 1}


def test_a_meal_never_planned_comes_before_any_that_was() -> None:
    planned = [(1, weeks_ago(52))]

    assert suggest([MON, TUE], [1, 2], planned) == {MON: 2, TUE: 1}


def test_only_the_most_recent_time_a_meal_was_cooked_counts() -> None:
    """Cooked ten weeks ago and again last week is recent."""
    planned = [(1, weeks_ago(10)), (1, weeks_ago(1)), (2, weeks_ago(4))]

    assert suggest([MON], [1, 2], planned) == {MON: 2}


def test_a_meal_already_planned_for_a_later_week_counts_as_recent() -> None:
    next_week = day_date(WEEK + timedelta(weeks=1), MON)
    planned = [(1, next_week), (2, weeks_ago(3))]

    assert suggest([MON], [1, 2], planned) == {MON: 2}


def test_nothing_planned_this_week_is_suggested_again() -> None:
    assert suggest([MON, TUE], [1, 2, 3], this_week=[2]) == {MON: 1, TUE: 3}


def test_this_weeks_own_days_do_not_make_a_meal_look_recent() -> None:
    """What is being filled is this week: its saved days are not history."""
    planned = [(1, day_date(WEEK, FRI)), (2, weeks_ago(2))]

    assert suggest([MON], [1, 2], planned) == {MON: 1}


def test_only_empty_days_are_filled_in_day_order() -> None:
    assert suggest([SUN, WED], [1, 2]) == {WED: 1, SUN: 2}


def test_with_too_few_meals_the_last_days_stay_empty() -> None:
    assert suggest([MON, TUE, WED], [7]) == {MON: 7}


def test_ties_go_to_the_meal_made_first() -> None:
    planned = [(5, weeks_ago(2)), (3, weeks_ago(2))]

    assert suggest([MON, TUE], [5, 3], planned) == {MON: 3, TUE: 5}


def test_nothing_to_fill() -> None:
    assert suggest([], [1, 2]) == {}
    assert suggest([MON], []) == {}
