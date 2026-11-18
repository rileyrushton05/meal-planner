"""SQLModel tables and the domain enums they use.

Deliberately omits ``from __future__ import annotations``: SQLModel reads
these annotations at class-creation time to build the columns, and
stringifying them breaks that.

There are no ORM ``Relationship`` declarations. Every read that needs a
meal with its ingredients is an explicit join in
:mod:`app.repositories`, which is what keeps a week's grocery list to one
query instead of lazy-loading one per row.

Database conventions (see docs/conventions.md): plural snake_case table
names; every constraint named through the metadata naming convention;
invariants enforced by named check and unique constraints rather than only
in Python; every foreign key indexed and given a deliberate ``ondelete``;
``created_at`` and ``updated_at`` on every table, set by the database.
tests/test_conventions.py holds the schema to all of this.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    func,
    text,
    true,
)
from sqlmodel import Field, SQLModel

#: Gives every constraint and index a stable, predictable name, so a
#: migration can refer to one by name and the database never invents its
#: own (Postgres would say `meal_pkey`, SQLite nothing at all).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
SQLModel.metadata.naming_convention = NAMING_CONVENTION


class _HasId(Protocol):
    id: int | None


def persisted_id(row: _HasId) -> int:
    """The primary key of a row that has been flushed or loaded.

    SQLModel types ``id`` as ``int | None`` because a row has no key until
    the database assigns one. Past that point a missing key is a bug, and
    this says so rather than letting ``None`` travel on into a query or a
    response.
    """
    if row.id is None:
        raise RuntimeError(f"{type(row).__name__} has no id; was it flushed?")
    return row.id


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


def _timestamp(*, onupdate: bool = False) -> Any:
    """A timezone-aware timestamp the database fills in.

    A server default rather than a Python one, so a row inserted by any
    writer - a migration, a script, psql - gets one too.
    """
    return Field(
        default=None,
        sa_column_kwargs={
            "server_default": func.now(),
            "nullable": False,
            **({"onupdate": func.now()} if onupdate else {}),
        },
        # SQLModel's annotation only admits a type here, but an instance is
        # what carries timezone=True, and SQLModel accepts one at runtime.
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )


class _Timestamps(SQLModel):
    created_at: datetime | None = _timestamp()
    updated_at: datetime | None = _timestamp(onupdate=True)


class User(_Timestamps, table=True):
    """Someone using the app.

    Three kinds, told apart by these columns rather than a type column:

    - a **guest** (`is_guest`): no credentials, identified only by a session
      cookie, deleted after a period without a visit;
    - an **account** (email and password hash): a guest who signed up keeps
      the same row, so everything they made comes with them;
    - an **unclaimed owner** (neither): the account the accounts migration
      gave the data that existed before accounts. Not a guest, so it is never
      cleaned up; it gains credentials when claimed.
    """

    __tablename__: str = "users"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        # Case-insensitively unique: "Riley@x.com" and "riley@x.com" are one
        # person. NULLs (guests) do not collide with each other.
        Index("uq_users_lower_email", text("lower(email)"), unique=True),
        CheckConstraint(
            "(email IS NULL) = (password_hash IS NULL)", name="credentials_complete"
        ),
        CheckConstraint("NOT is_guest OR email IS NULL", name="guests_have_no_email"),
        # Only an account with a login can recover it.
        CheckConstraint(
            "recovery_code_hash IS NULL OR email IS NOT NULL",
            name="recovery_code_needs_login",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    #: NULL for guests and the unclaimed owner.
    email: str | None = None
    #: NULL exactly when email is.
    password_hash: str | None = None
    #: SHA-256 of the recovery code (app/security.py), which only the person
    #: was ever shown. NULL for guests, and for accounts that have not made
    #: one yet (those from before recovery codes existed).
    recovery_code_hash: str | None = None
    is_guest: bool = Field(default=True, sa_column_kwargs={"server_default": true()})
    #: Drives guest cleanup.
    last_seen_at: datetime | None = _timestamp()


class Session(_Timestamps, table=True):
    """A signed-in browser. The cookie holds a random token; only its
    SHA-256 is stored, so a copy of this table cannot be replayed."""

    __tablename__: str = "sessions"  # pyright: ignore[reportIncompatibleVariableOverride]

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    expires_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
        index=True,
    )


class Meal(_Timestamps, table=True):
    """A recipe: a name, the servings it yields, and its ingredients."""

    __tablename__: str = "meals"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        # Unique per person, ignoring case: two people can both have
        # "Spaghetti Bolognese", one person cannot have it twice. Its leading
        # column also serves every lookup by owner.
        Index(
            "uq_meals_user_id_lower_name", "user_id", text("lower(name)"), unique=True
        ),
        CheckConstraint("servings >= 1", name="servings_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    name: str
    servings: int = 1


class Ingredient(_Timestamps, table=True):
    """A shopping item in one person's kitchen, shared by their meals.

    Per person rather than global: a shared table would let one person's
    spelling become everyone's, and would suggest strangers' ingredients in
    the autocomplete.
    """

    __tablename__: str = "ingredients"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        Index(
            "uq_ingredients_user_id_lower_name",
            "user_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    name: str


class MealIngredient(_Timestamps, table=True):
    """Pairs a meal with an ingredient, and how much of it."""

    __tablename__: str = "meal_ingredients"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    #: Deleting a meal deletes its ingredient lines with it.
    meal_id: int = Field(foreign_key="meals.id", ondelete="CASCADE", primary_key=True)
    #: An ingredient still on a meal cannot be deleted out from under it.
    #: NO ACTION, not RESTRICT: RESTRICT is checked the moment a row goes,
    #: so deleting an account - which cascades to its meals and ingredients
    #: in whatever order the database picks - failed on SQLite whenever the
    #: ingredients went first. NO ACTION is checked at the end of the
    #: statement, by which time the meal's lines are gone too.
    #: Declared through SQLAlchemy because SQLModel's `ondelete` only admits
    #: CASCADE, SET NULL and RESTRICT.
    ingredient_id: int = Field(
        sa_column_args=[ForeignKey("ingredients.id", ondelete="NO ACTION")],
        primary_key=True,
        index=True,
    )
    qty: float
    #: Empty for count-based items ("2 onions").
    unit: str = Field(default="", sa_column_kwargs={"server_default": ""})


class WeeklyPlan(_Timestamps, table=True):
    """The meal assigned to one day of one week, for one person.

    Keyed by (user, week, day), so planning next week never overwrites this
    one and two people can both plan a Monday. A row with no meal is a day
    deliberately cleared, as distinct from a day never set (no row).
    """

    __tablename__: str = "weekly_plans"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        Index(
            "uq_weekly_plans_user_id_week_start_date_day_of_week",
            "user_id",
            "week_start_date",
            "day_of_week",
            unique=True,
        ),
        CheckConstraint(
            "day_of_week IN (" + ", ".join(f"'{day.value}'" for day in DayOfWeek) + ")",
            name="day_of_week_valid",
        ),
        CheckConstraint("servings IS NULL OR servings >= 1", name="servings_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    week_start_date: date
    day_of_week: str
    #: Deleting a meal clears the days it was planned on, keeping the row.
    meal_id: int | None = Field(
        default=None, foreign_key="meals.id", ondelete="SET NULL", index=True
    )
    #: Servings planned for this day. None means use the recipe unscaled.
    servings: int | None = None


class RateLimit(_Timestamps, table=True):
    """Recent attempts at one throttled thing, such as logins to one account
    from one network. See app/ratelimit.py for the rules.

    `subject` is a keyed hash (HMAC) of what is being limited, never the
    email or IP address itself: comparing is all the throttle needs, and a
    plain hash of an IPv4 address can be reversed by trying all four
    billion. Belongs to no user, so it has no row-level security policy.
    """

    __tablename__: str = "rate_limits"  # pyright: ignore[reportIncompatibleVariableOverride]

    #: Which rule, e.g. "login-account".
    scope: str = Field(primary_key=True)
    subject: str = Field(primary_key=True)
    #: Attempts counted since `window_started_at`.
    hits: int = 0
    window_started_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )
    #: Refused until then. NULL: not blocked.
    blocked_until: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )


#: Every table, so callers needing the full list do not have to keep one.
ALL_TABLES: tuple[type[SQLModel], ...] = (
    User,
    Session,
    Meal,
    Ingredient,
    MealIngredient,
    WeeklyPlan,
    RateLimit,
)

__all__ = [
    "ALL_TABLES",
    "NAMING_CONVENTION",
    "DayOfWeek",
    "Ingredient",
    "Meal",
    "MealIngredient",
    "RateLimit",
    "Session",
    "User",
    "WeeklyPlan",
    "persisted_id",
]
