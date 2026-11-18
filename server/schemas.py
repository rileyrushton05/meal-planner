"""Request and response shapes for the HTTP API.

Kept separate from the SQLModel tables so the wire format can evolve
independently of the database, and so responses never leak columns that
happen to exist but are nobody's business.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DayOfWeek


class RequestSchema(BaseModel):
    """Base for every request body. Unknown fields are a 422 rather than
    silently dropped, so a misspelt field fails loudly instead of being
    replaced by its default."""

    model_config = ConfigDict(extra="forbid")


class ResponseSchema(BaseModel):
    """Base for every response body.

    Documented in serialization mode, where a field with a default is still
    required: the server always sends it. Otherwise the generated TypeScript
    would mark `meal_id` or `ingredients` optional, and every client read
    would need a check for a value that is never missing.
    """

    model_config = ConfigDict(
        json_schema_mode_override="serialization",
        json_schema_serialization_defaults_required=True,
    )


class IngredientAmount(ResponseSchema):
    """One ingredient attached to a meal, with how much of it."""

    ingredient_id: int
    name: str
    qty: float
    unit: str


class MealRead(ResponseSchema):
    """A meal and everything needed to render it."""

    id: int
    name: str
    servings: int
    ingredients: list[IngredientAmount] = Field(default_factory=list)


class MealCreate(RequestSchema):
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


class IngredientAdd(RequestSchema):
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


class IngredientUpdate(RequestSchema):
    qty: float = Field(gt=0)
    unit: str = Field(default="", max_length=50)


class _DayFields(BaseModel):
    """One day of a week. A null meal_id clears the day."""

    #: The enum, so an unknown day is a 422 rather than a stored row that
    #: no client knows how to render.
    day: DayOfWeek
    meal_id: int | None = None
    servings: int | None = Field(default=None, ge=1)


class DayAssignment(_DayFields, ResponseSchema):
    """A day as the API returns it: every field present."""


class DayAssignmentWrite(_DayFields, RequestSchema):
    """A day as a client sends it: strict about unknown fields, lenient about
    omitted ones, which default to a cleared day."""


class WeekPlanWrite(RequestSchema):
    days: list[DayAssignmentWrite]


class WeekPlanRead(ResponseSchema):
    week_start: date
    days: list[DayAssignment]


class GroceryLine(ResponseSchema):
    """One shopping line. qty stays numeric so clients can sort or price it."""

    name: str
    qty: float
    unit: str
    display: str


class TemplateIngredientRead(ResponseSchema):
    name: str
    qty: float
    unit: str


class TemplateRead(ResponseSchema):
    name: str
    servings: int
    ingredients: list[TemplateIngredientRead]


class AppState(ResponseSchema):
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


class Credentials(RequestSchema):
    """An email and password, for signup and login.

    The bounds here only keep request bodies sane. The rules a password must
    meet at signup are checked in app/security.py, which can say exactly
    what is wrong, rather than with a generic validation error.
    """

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class Account(ResponseSchema):
    """Who is signed in. No id: the client never needs it, and a numeric id
    would tell anyone signing up roughly how many accounts exist."""

    email: str | None
    is_guest: bool


class GuestStart(RequestSchema):
    """Optional: ask for sample meals, planned in the week containing this
    date (the browser's own week, since the server cannot know its zone)."""

    sample_week: date | None = None


class AccountDeletion(RequestSchema):
    """Confirmation for deleting an account. An account with a login sends
    its password; a guest, who has none, sends nothing."""

    password: str | None = Field(default=None, max_length=1024)


class ExportedIngredient(ResponseSchema):
    name: str
    qty: float
    unit: str


class ExportedMeal(ResponseSchema):
    name: str
    servings: int
    ingredients: list[ExportedIngredient]


class ExportedDay(ResponseSchema):
    week_start: date
    day: DayOfWeek
    meal: str
    #: None when the day uses the recipe's own servings.
    servings: int | None


class ExportedAccount(ResponseSchema):
    email: str | None
    is_guest: bool
    created_at: datetime | None


class AccountExport(ResponseSchema):
    """Everything the app holds that is the caller's own, in a form a person
    can read and another program can import: names rather than internal
    ids, which mean nothing outside this database.

    Not included, because they are not content: the password hash, session
    tokens, and throttle records, which are keyed hashes of an email or
    network and expire on their own.
    """

    format: str = "meal-planner-export"
    version: int = 1
    exported_at: datetime
    account: ExportedAccount
    meals: list[ExportedMeal]
    plans: list[ExportedDay]
