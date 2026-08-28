"""Request and response shapes for the HTTP API.

Kept separate from the SQLModel tables so the wire format can evolve
independently of the database, and so responses never leak columns that
happen to exist but are nobody's business.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.models import DayOfWeek


class IngredientAmount(BaseModel):
    """One ingredient attached to a meal, with how much of it."""

    ingredient_id: int
    name: str
    qty: float
    unit: str


class MealRead(BaseModel):
    """A meal and everything needed to render it."""

    id: int
    name: str
    servings: int
    ingredients: list[IngredientAmount] = Field(default_factory=list)


class MealCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    servings: int = Field(default=1, ge=1)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Meal name cannot be blank.")
        return stripped


class MealUpdate(MealCreate):
    """Same fields as creation; every one is required on update."""


class IngredientAdd(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Greater than zero: an ingredient with no amount cannot be shopped for.
    qty: float = Field(gt=0)
    unit: str = Field(default="", max_length=50)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Ingredient name cannot be blank.")
        return stripped

    @field_validator("unit")
    @classmethod
    def _strip_unit(cls, value: str) -> str:
        return value.strip()


class IngredientUpdate(BaseModel):
    qty: float = Field(gt=0)
    unit: str = Field(default="", max_length=50)


class DayAssignment(BaseModel):
    """One day of a week. A null meal_id clears the day."""

    #: The enum, so an unknown day is a 422 rather than a stored row that
    #: no client knows how to render.
    day: DayOfWeek
    meal_id: int | None = None
    servings: int | None = Field(default=None, ge=1)


class WeekPlanWrite(BaseModel):
    days: list[DayAssignment]


class WeekPlanRead(BaseModel):
    week_start: date
    days: list[DayAssignment]


class GroceryLine(BaseModel):
    """One shopping line. qty stays numeric so clients can sort or price it."""

    name: str
    qty: float
    unit: str
    display: str


class TemplateIngredientRead(BaseModel):
    name: str
    qty: float
    unit: str


class TemplateRead(BaseModel):
    name: str
    servings: int
    ingredients: list[TemplateIngredientRead]


class AppState(BaseModel):
    """Everything the UI needs for one week, in a single response.

    The point of this endpoint is latency: the Streamlit version issued a
    separate query per section on every interaction, which is unnoticeable
    against a local file and painful across a network. One request, one
    round trip.
    """

    week_start: date
    meals: list[MealRead]
    ingredient_names: list[str]
    plan: list[DayAssignment]
    templates: list[TemplateRead]
