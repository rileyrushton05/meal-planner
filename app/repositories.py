"""Data-access layer.

Every repository is bound to one user when it is constructed, and every
query it runs is scoped to that user. There is no method that takes a user
per call, so there is no method where forgetting it is possible: an unscoped
query is not expressible through this module. (Row-level security in
Postgres sits behind this, for the case where that reasoning is wrong.)

Asking for another user's row behaves exactly like asking for a row that
does not exist, so the API answers 404 either way and never confirms that
someone else's id is real.

Repositories never open, commit or roll back a transaction. They are handed
a session already inside one (`Database.transaction()`), and whoever opened
it decides the outcome: for the API, one transaction per request, so
everything a request does lands together or not at all. Sessions are made
with autobegin off, so a statement outside that transaction raises instead
of silently starting one that nobody commits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from itertools import count
from typing import Any, cast

from sqlalchemy import ColumnElement, and_, delete, func, insert, or_, update
from sqlalchemy import select as sa_select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import CursorResult
from sqlmodel import Session, col, select

from app.catalog import (
    StoredIngredient,
    StoredItem,
    SyncPlan,
    catalog_key,
)
from app.exceptions import (
    DuplicateNameError,
    GroceryItemNotFoundError,
    GroceryLimitError,
    IngredientNotOnMealError,
    InvalidDayError,
    MealNotFoundError,
    UnitMismatchError,
)
from app.models import (
    MAX_MEAL_NAME_LENGTH,
    CatalogAlias,
    CatalogItem,
    Category,
    CheckState,
    DayOfWeek,
    GroceryCheck,
    GroceryExtra,
    GrocerySettings,
    GroceryUsual,
    Ingredient,
    Meal,
    MealIngredient,
    RateLimit,
    User,
    WeeklyPlan,
    grocery_key,
    persisted_id,
)
from app.models import Session as SessionRow
from app.parsing import canonical_unit
from app.templates import MealTemplate


def _dialect_insert(session: Session, model: type):
    """INSERT with the dialect's ON CONFLICT support (same API on both)."""
    if session.get_bind().dialect.name == "postgresql":
        return postgresql.insert(model)
    return sqlite.insert(model)


def _count_or_delete(
    session: Session, model: type, condition: ColumnElement[bool], *, dry_run: bool
) -> int:
    """How many rows match, deleting them unless this is a dry run."""
    if dry_run:
        return session.execute(
            sa_select(func.count()).select_from(model).where(condition)
        ).scalar_one()
    # A DELETE returns a CursorResult, which has the count; the generic
    # Result type `execute` is annotated with does not.
    deleted = cast(CursorResult[Any], session.execute(delete(model).where(condition)))
    return deleted.rowcount


def _as_day(day: DayOfWeek | str) -> str:
    """Validate a weekday, returning its canonical name."""
    try:
        return DayOfWeek(day).value
    except ValueError:
        raise InvalidDayError(f"'{day}' is not a day of the week.") from None


#: What a copy's name ends in: " (copy)", " (copy 2)".
_COPY_SUFFIX = re.compile(r" \(copy(?: \d+)?\)$", re.IGNORECASE)


class _Repository:
    """The session to work in and the user every query is scoped to.

    Every write flushes before returning, so a constraint violation is
    raised by the method that caused it rather than later, at commit, where
    it could no longer be told apart from any other failure.
    """

    def __init__(self, session: Session, *, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    @property
    def user_id(self) -> int:
        return self._user_id


class IngredientRepository(_Repository):
    """Reads over one user's ingredients."""

    def list_all(self) -> list[Ingredient]:
        """Every ingredient this user has used, for the autocomplete."""
        return list(
            self._session.exec(
                select(Ingredient).where(Ingredient.user_id == self._user_id)
            ).all()
        )


class MealRepository(_Repository):
    """Creates, reads and edits one user's meals and their ingredients."""

    # ------------------------------------------------------------- meals

    def list_all(self) -> list[Meal]:
        """Every meal this user has saved, oldest first.

        Ordered explicitly: without ORDER BY the database may return rows in
        any order, and the per-user name index made SQLite return them
        alphabetically, reshuffling the list on screen.
        """
        return list(
            self._session.exec(
                select(Meal).where(Meal.user_id == self._user_id).order_by(col(Meal.id))
            ).all()
        )

    def list_all_with_ingredients(
        self,
    ) -> list[tuple[Meal, list[tuple[MealIngredient, Ingredient]]]]:
        """Every meal with its ingredients, in two queries rather than one
        per meal - which would be a network round trip each in deployment."""
        meals = self.list_all()
        rows = self._session.exec(
            select(MealIngredient, Ingredient)
            .join(Ingredient, col(Ingredient.id) == MealIngredient.ingredient_id)
            .join(Meal, col(Meal.id) == MealIngredient.meal_id)
            .where(Meal.user_id == self._user_id)
        ).all()

        by_meal: dict[int | None, list[tuple[MealIngredient, Ingredient]]] = {}
        for link, ingredient in rows:
            by_meal.setdefault(link.meal_id, []).append((link, ingredient))

        return [(meal, by_meal.get(meal.id, [])) for meal in meals]

    def get_with_ingredients(
        self, meal_id: int
    ) -> tuple[Meal, list[tuple[MealIngredient, Ingredient]]]:
        """One meal and its ingredients. Raises MealNotFoundError."""
        meal = self._get_or_raise(meal_id)
        return meal, self._ingredients_of(meal_id)

    def add(self, name: str, servings: int = 1) -> Meal:
        """Create a meal. Raises DuplicateNameError if the name is taken."""
        self._assert_name_available(name)
        meal = Meal(user_id=self._user_id, name=name, servings=servings)
        self._session.add(meal)
        self._session.flush()
        return meal

    def add_from_template(self, template: MealTemplate) -> Meal:
        """Create a meal and its template ingredients.

        If an ingredient fails part-way, the error leaves the meal half-built
        inside the caller's transaction, and the caller's rollback removes it.
        """
        meal = self.add(template.name, template.servings)
        for item in template.ingredients:
            self._attach_ingredient(persisted_id(meal), item.name, item.qty, item.unit)
        return meal

    def duplicate(self, meal_id: int) -> Meal:
        """A copy of one of this user's meals, to make a variation of it: the
        same servings and ingredient lines, under the first free name of
        "Curry (copy)", "Curry (copy 2)"... Raises MealNotFoundError.

        The lines are copied as they are, pointing at the same ingredients,
        so nothing is looked up or parsed again.
        """
        source, lines = self.get_with_ingredients(meal_id)
        copy = self.add(self._name_for_copy(source.name), servings=source.servings)
        self._session.add_all(
            MealIngredient(
                meal_id=persisted_id(copy),
                ingredient_id=link.ingredient_id,
                qty=link.qty,
                unit=link.unit,
            )
            for link, _ in lines
        )
        self._session.flush()
        return copy

    def update(self, meal_id: int, name: str, servings: int) -> None:
        """Rename a meal or change its serving size.

        Raises MealNotFoundError, or DuplicateNameError if the name is taken.
        """
        meal = self._get_or_raise(meal_id)
        if name.lower() != meal.name.lower():
            self._assert_name_available(name, exclude_id=meal_id)
        meal.name = name
        meal.servings = servings
        self._session.flush()

    def delete(self, meal_id: int) -> None:
        """Delete a meal. Raises MealNotFoundError.

        Days it was planned on are cleared rather than deleted, servings
        included. Its ingredient lines go with it through the foreign key's
        `ON DELETE CASCADE`. (`ON DELETE SET NULL` on the plan's key would
        clear the meal too, but not the servings planned for it, so this
        clears both itself; the key remains the guarantee for any other
        writer.)
        """
        self._get_or_raise(meal_id)
        self._session.execute(
            update(WeeklyPlan)
            .where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.meal_id) == meal_id,
            )
            .values(meal_id=None, servings=None)
        )
        self._session.execute(
            delete(Meal).where(
                col(Meal.id) == meal_id, col(Meal.user_id) == self._user_id
            )
        )

    # ------------------------------------------------------- ingredients

    def list_ingredients(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        """The (amount, ingredient) pairs attached to one of this user's meals.
        Empty for a meal that is not theirs."""
        if self._find_meal(meal_id) is None:
            return []
        return self._ingredients_of(meal_id)

    def add_ingredient(
        self, meal_id: int, ingredient_name: str, qty: float, unit: str
    ) -> None:
        """Attach an ingredient, creating it if new.

        Re-adding an existing one accumulates the quantity. Raises
        UnitMismatchError if the meal already uses a different unit, and
        MealNotFoundError if the meal does not exist or is not this user's.
        """
        self._get_or_raise(meal_id)
        self._attach_ingredient(meal_id, ingredient_name, qty, unit)

    def update_ingredient(
        self, meal_id: int, ingredient_id: int, qty: float, unit: str
    ) -> None:
        """Overwrite the quantity and unit of one ingredient on a meal.

        Raises IngredientNotOnMealError if it is not attached. Returning
        quietly instead would answer 200 to a request that changed nothing.
        """
        link = self._require_link(meal_id, ingredient_id)
        link.qty = qty
        link.unit = canonical_unit(unit)
        self._session.flush()

    def replace_ingredients(
        self, meal_id: int, items: Iterable[tuple[str, float, str]]
    ) -> None:
        """Make a meal's ingredients exactly `items` (name, qty, unit).

        The same ingredient twice in one unit adds up, as adding it twice
        does; in two different units it raises UnitMismatchError, and the
        caller's rollback leaves the list as it was. Raises
        MealNotFoundError for a meal that is not this user's.
        """
        self._get_or_raise(meal_id)
        self._session.execute(
            delete(MealIngredient).where(col(MealIngredient.meal_id) == meal_id)
        )
        for name, qty, unit in items:
            self._attach_ingredient(meal_id, name, qty, unit)

    def remove_ingredient(self, meal_id: int, ingredient_id: int) -> None:
        """Detach an ingredient from a meal, leaving the ingredient itself.

        Raises IngredientNotOnMealError if it is not attached.
        """
        self._session.delete(self._require_link(meal_id, ingredient_id))
        self._session.flush()

    # ----------------------------------------------------------- helpers

    def _find_meal(self, meal_id: int) -> Meal | None:
        meal = self._session.get(Meal, meal_id)
        # Someone else's meal is indistinguishable from no meal at all.
        if meal is None or meal.user_id != self._user_id:
            return None
        return meal

    def _get_or_raise(self, meal_id: int) -> Meal:
        meal = self._find_meal(meal_id)
        if meal is None:
            raise MealNotFoundError(f"No meal with id {meal_id}.")
        return meal

    def _ingredients_of(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        return list(
            self._session.exec(
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            ).all()
        )

    def _assert_name_available(
        self, name: str, *, exclude_id: int | None = None
    ) -> None:
        statement = select(Meal).where(
            Meal.user_id == self._user_id, func.lower(Meal.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(Meal.id != exclude_id)
        existing = self._session.exec(statement).first()
        if existing:
            raise DuplicateNameError(f"A meal named '{existing.name}' already exists.")

    def _name_for_copy(self, name: str) -> str:
        """The first of "Curry (copy)", "Curry (copy 2)"... no meal has.

        A copy of a copy counts on from the original's name rather than
        stacking up "(copy) (copy)", and a long name is shortened to leave
        room for the suffix.
        """
        base = _COPY_SUFFIX.sub("", name) or name
        taken = {
            existing.lower()
            for existing in self._session.exec(
                select(Meal.name).where(Meal.user_id == self._user_id)
            ).all()
        }
        for n in count(1):
            suffix = " (copy)" if n == 1 else f" (copy {n})"
            candidate = base[: MAX_MEAL_NAME_LENGTH - len(suffix)].rstrip() + suffix
            if candidate.lower() not in taken:
                return candidate
        raise AssertionError("unreachable")  # pragma: no cover

    def _find_link(self, meal_id: int, ingredient_id: int) -> MealIngredient | None:
        return self._session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id,
            )
        ).first()

    def _require_link(self, meal_id: int, ingredient_id: int) -> MealIngredient:
        """The link, or a domain error naming which half is missing."""
        self._get_or_raise(meal_id)
        link = self._find_link(meal_id, ingredient_id)
        if link is None:
            raise IngredientNotOnMealError(
                f"Ingredient {ingredient_id} is not on meal {meal_id}."
            )
        return link

    def _find_ingredient_by_name(self, name: str) -> Ingredient | None:
        """This user's ingredient of that name, ignoring case, so "Eggs" and
        "eggs" are one item."""
        return self._session.exec(
            select(Ingredient).where(
                Ingredient.user_id == self._user_id,
                func.lower(Ingredient.name) == name.lower(),
            )
        ).first()

    def _get_or_create_ingredient(self, name: str) -> Ingredient:
        """This user's ingredient of that name, created if it is new.

        Safe when two requests add the same new ingredient at once. A plain
        "look it up, insert it if missing" lets both see nothing and both
        insert; the unique index then rejects the second, and in Postgres
        that error poisons the rest of the transaction, so the whole request
        fails. `INSERT ... ON CONFLICT DO NOTHING` instead waits for the
        other insert, sees its row, and does nothing, and the lookup after it
        finds that row. The first lookup is only a shortcut: the ingredient
        usually exists already, and then one statement is enough.
        """
        existing = self._find_ingredient_by_name(name)
        if existing is not None:
            return existing

        self._session.execute(
            _dialect_insert(self._session, Ingredient)
            .values(
                user_id=self._user_id,
                name=name,
                catalog_item_id=CatalogRepository.item_matching(name),
            )
            .on_conflict_do_nothing(
                # The unique index `uq_ingredients_user_id_lower_name`.
                index_elements=[col(Ingredient.user_id), func.lower(Ingredient.name)]
            )
        )
        created = self._find_ingredient_by_name(name)
        if created is None:  # pragma: no cover - the insert or the conflict made it
            raise RuntimeError(f"Ingredient {name!r} vanished after its insert.")
        return created

    def _attach_ingredient(
        self, meal_id: int, name: str, qty: float, unit: str
    ) -> None:
        """Every unit is stored as the app spells it ("clove" as cloves), so
        amounts of one thing typed differently still add up."""
        unit = canonical_unit(unit)
        ingredient_id = persisted_id(self._get_or_create_ingredient(name))
        link = self._find_link(meal_id, ingredient_id)
        if link is None:
            self._session.add(
                MealIngredient(
                    meal_id=meal_id,
                    ingredient_id=ingredient_id,
                    qty=qty,
                    unit=unit,
                )
            )
            self._session.flush()
            return

        # Compared as spelled now: a line saved before units were tidied
        # may still say "clove".
        if canonical_unit(link.unit) != unit:
            raise UnitMismatchError(
                f"{name} is already on this meal measured in '{link.unit}'. "
                f"Use the same unit to add more, or remove the existing entry first."
            )
        link.qty = link.qty + qty
        link.unit = unit
        self._session.flush()


class WeeklyPlanRepository(_Repository):
    """Reads and writes the meal assigned to each day of a given week."""

    def get_week(self, week_start_date: date) -> list[WeeklyPlan]:
        """Every stored day for one week. Days never set are absent."""
        statement = select(WeeklyPlan).where(
            WeeklyPlan.user_id == self._user_id,
            WeeklyPlan.week_start_date == week_start_date,
        )
        return list(self._session.exec(statement).all())

    def list_planned(self) -> list[WeeklyPlan]:
        """Every day with a meal, in every week, in calendar order: for the
        account export. Days cleared back to nothing are left out."""
        rows = self._session.exec(
            select(WeeklyPlan).where(
                WeeklyPlan.user_id == self._user_id,
                col(WeeklyPlan.meal_id).is_not(None),
            )
        ).all()
        order = {day.value: index for index, day in enumerate(DayOfWeek)}
        return sorted(rows, key=lambda p: (p.week_start_date, order[p.day_of_week]))

    def set_day(
        self,
        week_start_date: date,
        day: DayOfWeek | str,
        meal_id: int | None,
        servings: int | None = None,
    ) -> None:
        """Assign (or clear, with meal_id=None) the meal for one day."""
        self.set_week(week_start_date, {day: (meal_id, servings)})

    def set_week(
        self,
        week_start_date: date,
        assignments: dict[DayOfWeek | str, tuple[int | None, int | None]],
    ) -> None:
        """Assign several days of one week at once.

        `assignments` maps day -> (meal_id, servings); a None meal_id clears
        the day. A day at a time meant 14 statements and several seconds
        against a remote database.
        """
        if not assignments:
            return

        # Coerced rather than trusted: the column only holds weekday names,
        # and a clear domain error beats the check constraint's.
        wanted = {_as_day(day): value for day, value in assignments.items()}
        meal_ids = {meal_id for meal_id, _ in wanted.values() if meal_id is not None}

        # Only this user's meals. The foreign key would accept anyone's,
        # since a key check does not know who owns the row it points at.
        if meal_ids:
            found = set(
                self._session.exec(
                    select(Meal.id).where(
                        col(Meal.id).in_(meal_ids), Meal.user_id == self._user_id
                    )
                )
            )
            missing = sorted(meal_ids - found)
            if missing:
                raise MealNotFoundError(f"No meal with id {missing[0]}.")

        # Replace rather than read-then-update: eight round trips for a week
        # becomes two. Row ids are referenced nowhere. Cleared days keep a
        # row with a NULL meal_id, distinguishing them from days never set.
        self._session.execute(
            delete(WeeklyPlan).where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.week_start_date) == week_start_date,
                col(WeeklyPlan.day_of_week).in_(wanted),
            )
        )
        # A Core insert becomes one executemany; adding ORM objects would
        # emit an INSERT per row to read back ids nothing uses.
        self._session.execute(
            insert(WeeklyPlan),
            [
                {
                    "user_id": self._user_id,
                    "week_start_date": week_start_date,
                    "day_of_week": day,
                    "meal_id": meal_id,
                    "servings": servings,
                }
                for day, (meal_id, servings) in wanted.items()
            ],
        )

    def ingredient_rows_for_week(
        self, week_start_date: date
    ) -> list[tuple[str, float, str, int | None, int, str | None]]:
        """Every planned ingredient for a week: name, qty, unit, the planned
        and recipe serving counts, and the aisle (the catalogue item's
        category; None for an ingredient the catalogue does not know).

        One join rather than a query per meal and per ingredient, which cost
        48 statements for a full week - free on SQLite, ~2.4s over a network.

        SQLAlchemy's own select, because SQLModel's typed overloads stop at
        four columns and this needs six.
        """
        statement = (
            sa_select(
                col(Ingredient.name),
                col(MealIngredient.qty),
                col(MealIngredient.unit),
                col(WeeklyPlan.servings),
                col(Meal.servings),
                col(CatalogItem.category),
            )
            .select_from(WeeklyPlan)
            .join(Meal, col(Meal.id) == col(WeeklyPlan.meal_id))
            .join(MealIngredient, col(MealIngredient.meal_id) == col(Meal.id))
            .join(Ingredient, col(Ingredient.id) == col(MealIngredient.ingredient_id))
            .outerjoin(
                CatalogItem, col(CatalogItem.id) == col(Ingredient.catalog_item_id)
            )
            .where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.week_start_date) == week_start_date,
            )
        )
        return list(self._session.execute(statement).tuples().all())

    def copy_week(self, source_week: date, target_week: date) -> int:
        """Copy assigned days from one week onto another, returning the count.

        Unassigned source days are skipped rather than clearing the target.
        """
        source_plans = self.get_week(source_week)
        existing = {plan.day_of_week: plan for plan in self.get_week(target_week)}

        copied = 0
        for source in source_plans:
            if source.meal_id is None:
                continue
            target = existing.get(source.day_of_week)
            if target:
                target.meal_id = source.meal_id
                target.servings = source.servings
            else:
                self._session.add(
                    WeeklyPlan(
                        user_id=self._user_id,
                        week_start_date=target_week,
                        day_of_week=source.day_of_week,
                        meal_id=source.meal_id,
                        servings=source.servings,
                    )
                )
            copied += 1
        self._session.flush()
        return copied


#: Caps on what one person can store, far above any real shop.
MAX_EXTRAS_PER_WEEK = 100
MAX_USUALS = 100


class GroceryRepository(_Repository):
    """One user's grocery list state: what is ticked off or already at
    home, the extras on each week's list, their usuals, and their aisle
    order. The lines themselves are derived (app/groceries.py)."""

    # --- Ticks ---------------------------------------------------------------

    def checks(self, week_start_date: date) -> dict[str, CheckState]:
        """Each line key marked for the week, and how."""
        rows = self._session.exec(
            select(GroceryCheck).where(
                GroceryCheck.user_id == self._user_id,
                GroceryCheck.week_start_date == week_start_date,
            )
        )
        return {row.item_key: CheckState(row.state) for row in rows}

    def set_check(
        self, week_start_date: date, item_key: str, state: CheckState | None
    ) -> None:
        """Mark a line, or (None) put it back to get. One statement either
        way, so two devices ticking at once cannot collide."""
        if state is None:
            self._session.execute(
                delete(GroceryCheck).where(
                    col(GroceryCheck.user_id) == self._user_id,
                    col(GroceryCheck.week_start_date) == week_start_date,
                    col(GroceryCheck.item_key) == item_key,
                )
            )
            return
        self._session.execute(
            _dialect_insert(self._session, GroceryCheck)
            .values(
                user_id=self._user_id,
                week_start_date=week_start_date,
                item_key=item_key,
                state=state.value,
            )
            .on_conflict_do_update(
                index_elements=[
                    col(GroceryCheck.user_id),
                    col(GroceryCheck.week_start_date),
                    col(GroceryCheck.item_key),
                ],
                set_={"state": state.value, "updated_at": func.now()},
            )
        )

    def empty_basket(self, week_start_date: date) -> int:
        """Untick everything in the basket, keeping what is marked as
        already at home: that is still true when the shop starts again."""
        return _count_or_delete(
            self._session,
            GroceryCheck,
            and_(
                col(GroceryCheck.user_id) == self._user_id,
                col(GroceryCheck.week_start_date) == week_start_date,
                col(GroceryCheck.state) == CheckState.BASKET.value,
            ),
            dry_run=False,
        )

    def every_check(self) -> list[GroceryCheck]:
        """Every week's marks, for the account export."""
        return list(
            self._session.exec(
                select(GroceryCheck)
                .where(GroceryCheck.user_id == self._user_id)
                .order_by(col(GroceryCheck.week_start_date), col(GroceryCheck.item_key))
            )
        )

    # --- Extras --------------------------------------------------------------

    def every_extra(self) -> list[GroceryExtra]:
        """Every week's extras, for the account export."""
        return list(
            self._session.exec(
                select(GroceryExtra)
                .where(GroceryExtra.user_id == self._user_id)
                .order_by(col(GroceryExtra.week_start_date), col(GroceryExtra.id))
            )
        )

    def extras(self, week_start_date: date) -> list[tuple[GroceryExtra, str | None]]:
        """The week's extras, each with its aisle, oldest first."""
        statement = (
            select(GroceryExtra, CatalogItem.category)
            .outerjoin(
                CatalogItem,
                col(CatalogItem.id) == col(GroceryExtra.catalog_item_id),
            )
            .where(
                GroceryExtra.user_id == self._user_id,
                GroceryExtra.week_start_date == week_start_date,
            )
            .order_by(col(GroceryExtra.id))
        )
        return [(extra, category) for extra, category in self._session.exec(statement)]

    def add_extra(
        self, week_start_date: date, name: str, qty: float | None, unit: str
    ) -> None:
        """Put something on the week's list. Already there (by name, any
        case): its amount becomes this one, rather than a second line."""
        self._refuse_past(
            MAX_EXTRAS_PER_WEEK,
            and_(
                col(GroceryExtra.user_id) == self._user_id,
                col(GroceryExtra.week_start_date) == week_start_date,
                func.lower(GroceryExtra.name) != name.lower(),
            ),
            GroceryExtra,
            f"A week's list can hold {MAX_EXTRAS_PER_WEEK} extras; remove some first.",
        )
        unit = canonical_unit(unit)
        self._session.execute(
            _dialect_insert(self._session, GroceryExtra)
            .values(
                user_id=self._user_id,
                week_start_date=week_start_date,
                name=name,
                qty=qty,
                unit=unit,
                catalog_item_id=CatalogRepository.item_matching(name),
            )
            .on_conflict_do_update(
                # The unique index on (user, week, lower(name)).
                index_elements=[
                    col(GroceryExtra.user_id),
                    col(GroceryExtra.week_start_date),
                    func.lower(GroceryExtra.name),
                ],
                set_={"qty": qty, "unit": unit, "updated_at": func.now()},
            )
        )

    def extra(self, week_start_date: date, extra_id: int) -> GroceryExtra:
        """One extra on the week's list."""
        extra = self._session.exec(
            select(GroceryExtra).where(
                GroceryExtra.id == extra_id,
                GroceryExtra.user_id == self._user_id,
                GroceryExtra.week_start_date == week_start_date,
            )
        ).first()
        if extra is None:
            raise GroceryItemNotFoundError(
                "That item is no longer on this week's list."
            )
        return extra

    def remove_extra(self, week_start_date: date, extra_id: int) -> GroceryExtra:
        """Take an extra off the week's list, returning what it was."""
        extra = self.extra(week_start_date, extra_id)
        self._session.delete(extra)
        # Its tick goes with it, or adding it again would bring it back
        # already ticked.
        self.set_check(
            week_start_date, grocery_key(extra.name, extra.unit, extra=True), None
        )
        self._session.flush()
        return extra

    def add_usuals(self, week_start_date: date) -> int:
        """Put every usual on the week's list, except those already there
        by name (whose amount is left as it is). Returns how many were added."""
        on_list = {extra.name.lower() for extra, _ in self.extras(week_start_date)}
        added = 0
        for usual in self.usuals():
            if usual.name.lower() in on_list:
                continue
            self.add_extra(week_start_date, usual.name, usual.qty, usual.unit)
            added += 1
        return added

    # --- Usuals --------------------------------------------------------------

    def usuals(self) -> list[GroceryUsual]:
        """Alphabetical, as a list to scan."""
        return list(
            self._session.exec(
                select(GroceryUsual)
                .where(GroceryUsual.user_id == self._user_id)
                .order_by(func.lower(GroceryUsual.name))
            )
        )

    def add_usual(self, name: str, qty: float | None, unit: str) -> None:
        """Keep something as a usual; one of that name already kept takes
        this amount."""
        self._refuse_past(
            MAX_USUALS,
            and_(
                col(GroceryUsual.user_id) == self._user_id,
                func.lower(GroceryUsual.name) != name.lower(),
            ),
            GroceryUsual,
            f"You can keep {MAX_USUALS} usuals; remove some first.",
        )
        unit = canonical_unit(unit)
        self._session.execute(
            _dialect_insert(self._session, GroceryUsual)
            .values(user_id=self._user_id, name=name, qty=qty, unit=unit)
            .on_conflict_do_update(
                # The unique index `uq_grocery_usuals_user_id_lower_name`.
                index_elements=[
                    col(GroceryUsual.user_id),
                    func.lower(GroceryUsual.name),
                ],
                set_={"qty": qty, "unit": unit, "updated_at": func.now()},
            )
        )

    def remove_usual(self, usual_id: int) -> None:
        removed = _count_or_delete(
            self._session,
            GroceryUsual,
            and_(
                col(GroceryUsual.id) == usual_id,
                col(GroceryUsual.user_id) == self._user_id,
            ),
            dry_run=False,
        )
        if not removed:
            raise GroceryItemNotFoundError("That is no longer one of your usuals.")

    def _refuse_past(
        self, limit: int, others: ColumnElement[bool], model: type, message: str
    ) -> None:
        """A cap on rows a person can pile up, counting the others: adding
        again under a name already there changes it, so is always allowed.
        Not race-proof, and needs not be: it bounds storage, not money."""
        if _count_or_delete(self._session, model, others, dry_run=True) >= limit:
            raise GroceryLimitError(message)

    # --- Aisle order ---------------------------------------------------------

    def aisle_order(self) -> list[Category]:
        """The person's own order, or the default (`Category` order). An
        aisle added to the app after they chose goes at the end."""
        settings = self._session.get(GrocerySettings, self._user_id)
        if settings is None:
            return list(Category)
        known = {category.value for category in Category}
        chosen = [
            Category(value)
            for value in settings.aisle_order.split(",")
            if value in known
        ]
        return chosen + [category for category in Category if category not in chosen]

    def set_aisle_order(self, order: list[Category]) -> None:
        """`order` must name every aisle once; the API checks that."""
        value = ",".join(category.value for category in order)
        self._session.execute(
            _dialect_insert(self._session, GrocerySettings)
            .values(user_id=self._user_id, aisle_order=value)
            .on_conflict_do_update(
                index_elements=[col(GrocerySettings.user_id)],
                set_={"aisle_order": value, "updated_at": func.now()},
            )
        )


class UserRepository:
    """Accounts. Not bound to a user, since its job is to find one."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def create(self, *, is_guest: bool = True) -> User:
        user = User(is_guest=is_guest)
        self._session.add(user)
        self._session.flush()
        return user

    def create_account(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash, is_guest=False)
        self._session.add(user)
        self._session.flush()
        return user

    def find_by_email(self, email: str) -> User | None:
        """The account with that email, ignoring case (the unique index is on
        `lower(email)`, which this matches so it can use it)."""
        return self._session.exec(
            select(User).where(func.lower(User.email) == email.lower())
        ).first()

    def set_credentials(self, user: User, email: str, password_hash: str) -> None:
        """Give a guest (or the unclaimed owner) an email and password. The
        row, and so everything it owns, stays the same."""
        user.email = email
        user.password_hash = password_hash
        user.is_guest = False
        self._session.flush()

    def set_password_hash(self, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        self._session.flush()

    def set_recovery_code_hash(self, user: User, recovery_code_hash: str) -> None:
        user.recovery_code_hash = recovery_code_hash
        self._session.flush()

    def unclaimed_owners(self) -> list[User]:
        """Accounts with no credentials that are not guests: the one the
        accounts migration created to hold the data from before accounts,
        until someone claims it. There should be at most one."""
        return list(
            self._session.exec(
                select(User)
                .where(col(User.is_guest).is_(False), col(User.email).is_(None))
                .order_by(col(User.id))
            ).all()
        )

    def purge_idle_guests(self, seen_before: datetime, *, dry_run: bool) -> int:
        """Delete guests not seen since `seen_before`, and through ON DELETE
        CASCADE everything they made and their sessions. Accounts, and the
        unclaimed owner, are never guests, so are never touched."""
        return _count_or_delete(
            self._session,
            User,
            and_(col(User.is_guest).is_(True), col(User.last_seen_at) < seen_before),
            dry_run=dry_run,
        )

    def delete_with_everything(self, user_id: int) -> dict[str, int]:
        """Delete an account and, through ON DELETE CASCADE, every row it
        owns, returning how many of each kind went.

        One DELETE, so it all goes or none of it does. The counts are taken
        first, in the same transaction; on Postgres they read tables under
        row security, so the caller must have declared the user (`act_as`).
        """
        removed = {
            kind: _count_or_delete(
                self._session, model, col(model.user_id) == user_id, dry_run=True
            )
            for kind, model in (
                ("meals", Meal),
                ("ingredients", Ingredient),
                ("plans", WeeklyPlan),
                ("sessions", SessionRow),
            )
        }
        _count_or_delete(self._session, User, col(User.id) == user_id, dry_run=False)
        return removed

    def touch(self, user_id: int, now: datetime) -> None:
        """Record a visit, which keeps a guest from being cleaned up."""
        self._session.execute(
            update(User).where(col(User.id) == user_id).values(last_seen_at=now)
        )


class SessionRepository:
    """Signed-in browsers, found by the SHA-256 of their cookie."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        self._session.add(
            SessionRow(token_hash=token_hash, user_id=user_id, expires_at=expires_at)
        )
        self._session.flush()

    def find_live(
        self, token_hash: str, now: datetime
    ) -> tuple[SessionRow, User] | None:
        """The session and its user, if the session exists and has not
        expired. One query: this runs on every request."""
        return self._session.exec(
            select(SessionRow, User)
            .join(User, col(User.id) == SessionRow.user_id)
            .where(SessionRow.token_hash == token_hash, SessionRow.expires_at > now)
        ).first()

    def extend(self, token_hash: str, expires_at: datetime) -> None:
        self._session.execute(
            update(SessionRow)
            .where(col(SessionRow.token_hash) == token_hash)
            .values(expires_at=expires_at)
        )

    def delete(self, token_hash: str) -> None:
        self._session.execute(
            delete(SessionRow).where(col(SessionRow.token_hash) == token_hash)
        )

    def delete_all_for(self, user_id: int) -> int:
        """End every session of one account, wherever it is signed in."""
        mine = col(SessionRow.user_id) == user_id
        return _count_or_delete(self._session, SessionRow, mine, dry_run=False)

    def purge_expired(self, now: datetime, *, dry_run: bool) -> int:
        """Delete sessions past their expiry, which can never sign in again."""
        expired = col(SessionRow.expires_at) <= now
        return _count_or_delete(self._session, SessionRow, expired, dry_run=dry_run)


class RateLimitRepository:
    """Throttle buckets (app/ratelimit.py), one row per scope and subject."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self, scope: str, subject: str, *, for_update: bool = False
    ) -> RateLimit | None:
        """The bucket, or None. With `for_update`, the row is created if
        missing and then locked until the transaction ends, so concurrent
        attempts are counted one after another instead of both reading the
        same count. The created row has no hits, which reads like no row."""
        if for_update:
            self._session.execute(
                _dialect_insert(self._session, RateLimit)
                .values(
                    scope=scope,
                    subject=subject,
                    hits=0,
                    window_started_at=func.now(),
                )
                .on_conflict_do_nothing(index_elements=["scope", "subject"])
            )
        statement = select(RateLimit).where(
            RateLimit.scope == scope, RateLimit.subject == subject
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session.exec(statement.execution_options(populate_existing=True))
        found = row.first()
        if found is not None and found.hits == 0 and found.blocked_until is None:
            return None
        return found

    def save(
        self,
        scope: str,
        subject: str,
        *,
        hits: int,
        window_started_at: datetime,
        blocked_until: datetime | None,
    ) -> None:
        """Write a bucket whose row `get(..., for_update=True)` created."""
        self._session.execute(
            update(RateLimit)
            .where(col(RateLimit.scope) == scope, col(RateLimit.subject) == subject)
            .values(
                hits=hits,
                window_started_at=window_started_at,
                blocked_until=blocked_until,
            )
        )

    def delete(self, scope: str, subject: str) -> None:
        self._session.execute(
            delete(RateLimit).where(
                col(RateLimit.scope) == scope, col(RateLimit.subject) == subject
            )
        )

    def purge_stale(
        self, started_before: datetime, now: datetime, *, dry_run: bool
    ) -> int:
        """Delete buckets that can no longer refuse or count anything: their
        window began before `started_before` and they are not blocked."""
        return _count_or_delete(
            self._session,
            RateLimit,
            and_(
                col(RateLimit.window_started_at) < started_before,
                or_(
                    col(RateLimit.blocked_until).is_(None),
                    col(RateLimit.blocked_until) <= now,
                ),
            ),
            dry_run=dry_run,
        )


class CatalogRepository:
    """The ingredient catalogue (app/catalog.py): read by everyone, written
    only by the sync job, which runs as the database owner."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def item_matching(name: str) -> Any:
        """The id of the catalogue item a name means, as a subquery, so an
        ingredient is linked in the same statement that creates it. NULL when
        nothing matches."""
        return (
            sa_select(col(CatalogAlias.catalog_item_id))
            .where(col(CatalogAlias.alias_key) == catalog_key(name))
            .scalar_subquery()
        )

    def items(self) -> list[StoredItem]:
        return [
            StoredItem(
                persisted_id(item),
                item.name,
                item.name_key,
                item.category,
                item.measure,
                item.each_grams,
            )
            for item in self._session.exec(
                select(CatalogItem).order_by(col(CatalogItem.id))
            )
        ]

    def every_ingredient(self) -> list[StoredIngredient]:
        """Every user's ingredients: the sync job relinks them all."""
        return [
            StoredIngredient(persisted_id(row), row.name, row.catalog_item_id)
            for row in self._session.exec(
                select(Ingredient).order_by(col(Ingredient.id))
            )
        ]

    def apply(self, plan: SyncPlan) -> None:
        """Make the catalogue and every ingredient's link match the plan."""
        for entry in plan.add:
            self._session.add(
                CatalogItem(
                    name=entry.name,
                    name_key=entry.name_key,
                    category=entry.category.value,
                    measure=entry.measure.value,
                    each_grams=entry.each_grams,
                )
            )
        for entry in plan.update:
            self._session.execute(
                update(CatalogItem)
                .where(col(CatalogItem.name_key) == entry.name_key)
                .values(
                    name=entry.name,
                    category=entry.category.value,
                    measure=entry.measure.value,
                    each_grams=entry.each_grams,
                )
            )
        if plan.remove:
            # Their aliases go with them; ingredients linked to them are
            # unlinked by ON DELETE SET NULL.
            self._session.execute(
                delete(CatalogItem).where(col(CatalogItem.id).in_(plan.remove))
            )
        self._session.flush()

        id_of = {item.name_key: item.id for item in self.items()}
        wanted = {alias: id_of[key] for alias, key in plan.aliases.items()}
        stored = {
            alias.alias_key: alias.catalog_item_id
            for alias in self._session.exec(select(CatalogAlias))
        }
        stale = [alias for alias, item in stored.items() if wanted.get(alias) != item]
        if stale:
            self._session.execute(
                delete(CatalogAlias).where(col(CatalogAlias.alias_key).in_(stale))
            )
        fresh = [
            {"alias_key": alias, "catalog_item_id": item}
            for alias, item in wanted.items()
            if stored.get(alias) != item
        ]
        if fresh:
            self._session.execute(insert(CatalogAlias), fresh)

        for ingredient_id, key in plan.relink.items():
            self._session.execute(
                update(Ingredient)
                .where(col(Ingredient.id) == ingredient_id)
                .values(catalog_item_id=id_of[key] if key else None)
            )
        self._session.flush()
