"""SQLModel tables and the domain enums they use.

Deliberately omits ``from __future__ import annotations``: SQLAlchemy
resolves ``Relationship`` targets from real annotation objects, and
stringifying them breaks that lookup.
"""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class DayOfWeek(StrEnum):
    """The seven days. Declaration order is display order, so `list(DayOfWeek)`
    is the single source of truth for "Monday first"."""

    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


class MealIngredient(SQLModel, table=True):
    """Pairs a meal with an ingredient, and how much of it."""

    meal_id: int | None = Field(default=None, foreign_key="meal.id", primary_key=True)
    ingredient_id: int | None = Field(
        default=None, foreign_key="ingredient.id", primary_key=True
    )

    qty: float | None = None
    unit: str | None = None


class Meal(SQLModel, table=True):
    """A recipe: a name, the servings it yields, and its ingredients."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    servings: int = 1
    # sa_type is explicit because the default maps to a naive column, and
    # Postgres would then drop the UTC offset. Invisible on SQLite.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
    )

    ingredients: list["Ingredient"] = Relationship(
        back_populates="meals", link_model=MealIngredient
    )


class Ingredient(SQLModel, table=True):
    """A shopping item, shared across every meal that uses it."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    meals: list[Meal] = Relationship(
        back_populates="ingredients", link_model=MealIngredient
    )


class WeeklyPlan(SQLModel, table=True):
    """The meal assigned to one day of one week.

    Keyed by (week_start_date, day_of_week), so planning next week never
    overwrites this one.
    """

    __table_args__ = (
        UniqueConstraint(
            "week_start_date", "day_of_week", name="uq_weeklyplan_week_day"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    week_start_date: date = Field(index=True)
    day_of_week: str = Field(index=True)
    meal_id: int | None = Field(default=None, foreign_key="meal.id")
    #: Servings planned for this day. None means use the recipe unscaled.
    servings: int | None = None
