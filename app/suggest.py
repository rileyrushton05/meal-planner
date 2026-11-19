"""Suggesting meals for a week's empty days: the ones not cooked recently.

Each meal is scored by how near the week its closest other planned day is,
before or after: a meal planned last week, or already next week, is a poor
suggestion; one last cooked two months ago is a good one, and one never
planned is the best. Nothing already planned this week is suggested again,
and with fewer meals than empty days the rest stay empty rather than one
meal filling two nights.

Pure and deterministic (ties go to the older meal), so the same week and
history always suggest the same meals, and the tests can say exactly which.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from app.models import DayOfWeek


def day_date(week_start: date, day: DayOfWeek) -> date:
    return week_start + timedelta(days=list(DayOfWeek).index(day))


def suggest_for_empty_days(
    *,
    week_start: date,
    empty: Sequence[DayOfWeek],
    meal_ids: Iterable[int],
    planned: Iterable[tuple[int, date]],
    already_this_week: Iterable[int] = (),
) -> dict[DayOfWeek, int]:
    """A meal for each empty day, in day order, while meals last.

    `planned` is (meal id, date) for every planned day in any week; days in
    this week are ignored, since this week is what is being filled.
    """
    week_end = week_start + timedelta(days=6)
    nearest: dict[int, int] = {}
    for meal_id, when in planned:
        if week_start <= when <= week_end:
            continue
        gap = (week_start - when).days if when < week_start else (when - week_end).days
        nearest[meal_id] = min(gap, nearest.get(meal_id, gap))

    taken = set(already_this_week)
    candidates = sorted(
        (m for m in set(meal_ids) if m not in taken),
        # Never planned first, then the longest gap; on a tie, the meal made
        # first. A missing gap sorts as infinitely long.
        key=lambda m: (-nearest[m] if m in nearest else float("-inf"), m),
    )
    days = [day for day in DayOfWeek if day in set(empty)]
    return dict(zip(days, candidates, strict=False))
