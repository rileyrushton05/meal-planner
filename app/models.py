"""SQLModel table definitions and the domain enums they rely on.

Note: this module deliberately omits ``from __future__ import annotations``.
SQLAlchemy resolves ``Relationship`` targets from real annotation objects at
class-creation time, and stringifying them breaks that lookup.
"""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class DayOfWeek(StrEnum):
    """The seven days, in the order the planner displays them.

    Declaration order is the display order, so `list(DayOfWeek)` is the
    single source of truth for "Monday first" and callers never hand-roll
    a day list. Stored in the database as its plain string value, which
    keeps existing rows readable and needs no migration.
    """

    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"

    @property
    def short_name(self) -> str:
        """Three-letter abbreviation, e.g. "Mon"."""
        return self.value[:3]


class MealIngredient(SQLModel, table=True):
    """Join row pairing a meal with an ingredient, plus how much of it."""

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    ingredients: list["Ingredient"] = Relationship(
        back_populates="meals", link_model=MealIngredient
    )


class Ingredient(SQLModel, table=True):
    """A single shopping item, shared across every meal that uses it."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    meals: list[Meal] = Relationship(
        back_populates="ingredients", link_model=MealIngredient
    )


class WeeklyPlan(SQLModel, table=True):
    """One day of one week, and the meal assigned to it.

    Keyed by (week_start_date, day_of_week) so each week is independent
    and planning next week never overwrites this one.
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
    #: Servings actually planned for this day, which may differ from the
    #: meal's own base servings (e.g. cooking a serves-4 recipe for 2).
    #: None means "use the meal's base servings unscaled".
    servings: int | None = None
