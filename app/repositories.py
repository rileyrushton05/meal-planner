"""Data-access layer.

Each repository is constructed with a :class:`~app.db.Database` and runs
every method inside a single transaction, so multi-step writes either land
completely or not at all. Callers never open sessions themselves.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, insert
from sqlmodel import Session, col, select

from app.db import Database
from app.exceptions import DuplicateNameError, MealNotFoundError, UnitMismatchError
from app.models import DayOfWeek, Ingredient, Meal, MealIngredient, WeeklyPlan
from app.templates import MealTemplate


def _find_ingredient_by_name(session: Session, name: str) -> Ingredient | None:
    """Look up an ingredient ignoring case, so "Eggs" and "eggs" are one item."""
    return session.exec(
        select(Ingredient).where(func.lower(Ingredient.name) == name.lower())
    ).first()


class IngredientRepository:
    """Reads over the shared ingredient catalogue."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def list_all(self) -> list[Ingredient]:
        """Every ingredient known to the app, across all meals."""
        with self._db.session() as session:
            return list(session.exec(select(Ingredient)).all())

    def search_names(self, term: str) -> list[str]:
        """Ingredient names containing `term`, for the autocomplete picker."""
        names = [ingredient.name for ingredient in self.list_all()]
        if not term:
            return names
        lowered = term.lower()
        return [name for name in names if lowered in name.lower()]


class MealRepository:
    """Creates, reads and edits meals and the ingredients attached to them."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------- meals

    def list_all(self) -> list[Meal]:
        """Every saved meal."""
        with self._db.session() as session:
            return list(session.exec(select(Meal)).all())

    def list_all_with_ingredients(
        self,
    ) -> list[tuple[Meal, list[tuple[MealIngredient, Ingredient]]]]:
        """Every meal paired with its ingredients, in two queries total.

        Calling list_ingredients per meal instead would be one query per
        meal - fine locally, one network round trip each in deployment.
        """
        with self._db.session() as session:
            meals = list(session.exec(select(Meal)).all())

            rows = session.exec(
                select(MealIngredient, Ingredient).where(
                    MealIngredient.ingredient_id == Ingredient.id
                )
            ).all()

        by_meal: dict[int, list[tuple[MealIngredient, Ingredient]]] = {}
        for link, ingredient in rows:
            by_meal.setdefault(link.meal_id, []).append((link, ingredient))

        return [(meal, by_meal.get(meal.id, [])) for meal in meals]

    def get_with_ingredients(
        self, meal_id: int
    ) -> tuple[Meal, list[tuple[MealIngredient, Ingredient]]]:
        """One meal and its ingredients.

        Raises:
            MealNotFoundError: if the meal doesn't exist.
        """
        with self._db.session() as session:
            meal = self._get_or_raise(session, meal_id)
            rows = session.exec(
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            ).all()
            return meal, list(rows)

    def add(self, name: str, servings: int = 1) -> Meal:
        """Create a meal.

        Raises:
            DuplicateNameError: if a meal with that name already exists.
        """
        with self._db.session() as session:
            self._assert_name_available(session, name)
            meal = Meal(name=name, servings=servings)
            session.add(meal)
            session.flush()
            return meal

    def add_from_template(self, template: MealTemplate) -> Meal:
        """Create a meal and all of its template ingredients in one transaction.

        Raises:
            DuplicateNameError: if a meal with that name already exists.
        """
        with self._db.session() as session:
            self._assert_name_available(session, template.name)
            meal = Meal(name=template.name, servings=template.servings)
            session.add(meal)
            session.flush()

            for item in template.ingredients:
                self._attach_ingredient(session, meal.id, item.name, item.qty, item.unit)
            return meal

    def update(self, meal_id: int, name: str, servings: int) -> None:
        """Rename a meal and/or change its base serving size.

        Raises:
            MealNotFoundError: if the meal doesn't exist.
            DuplicateNameError: if another meal already has that name.
        """
        with self._db.session() as session:
            meal = self._get_or_raise(session, meal_id)
            if name.lower() != meal.name.lower():
                self._assert_name_available(session, name, exclude_id=meal_id)
            meal.name = name
            meal.servings = servings

    def delete(self, meal_id: int) -> None:
        """Delete a meal, its ingredient links, and any day assignments.

        Days the meal was planned on are left in place but unassigned,
        rather than being deleted outright.

        Raises:
            MealNotFoundError: if the meal doesn't exist.
        """
        with self._db.session() as session:
            meal = self._get_or_raise(session, meal_id)

            links = session.exec(
                select(MealIngredient).where(MealIngredient.meal_id == meal_id)
            ).all()
            for link in links:
                session.delete(link)

            plans = session.exec(
                select(WeeklyPlan).where(WeeklyPlan.meal_id == meal_id)
            ).all()
            for plan in plans:
                plan.meal_id = None
                plan.servings = None

            session.delete(meal)

    # ------------------------------------------------------- ingredients

    def list_ingredients(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        """The (amount, ingredient) pairs attached to a meal."""
        with self._db.session() as session:
            statement = (
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            )
            return list(session.exec(statement).all())

    def add_ingredient(
        self, meal_id: int, ingredient_name: str, qty: float, unit: str
    ) -> None:
        """Attach an ingredient to a meal, creating the ingredient if new.

        Adding an ingredient the meal already has accumulates the quantity
        rather than creating a second row.

        Raises:
            UnitMismatchError: if the meal already measures that ingredient
                in a different unit.
        """
        with self._db.session() as session:
            self._attach_ingredient(session, meal_id, ingredient_name, qty, unit)

    def update_ingredient(
        self, meal_id: int, ingredient_id: int, qty: float, unit: str
    ) -> None:
        """Overwrite the quantity and unit of one ingredient on a meal."""
        with self._db.session() as session:
            link = self._find_link(session, meal_id, ingredient_id)
            if link:
                link.qty = qty
                link.unit = unit

    def remove_ingredient(self, meal_id: int, ingredient_id: int) -> None:
        """Detach an ingredient from a meal, leaving the ingredient itself."""
        with self._db.session() as session:
            link = self._find_link(session, meal_id, ingredient_id)
            if link:
                session.delete(link)

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _get_or_raise(session: Session, meal_id: int) -> Meal:
        meal = session.get(Meal, meal_id)
        if meal is None:
            raise MealNotFoundError(f"No meal with id {meal_id}.")
        return meal

    @staticmethod
    def _assert_name_available(
        session: Session, name: str, *, exclude_id: int | None = None
    ) -> None:
        statement = select(Meal).where(func.lower(Meal.name) == name.lower())
        if exclude_id is not None:
            statement = statement.where(Meal.id != exclude_id)
        existing = session.exec(statement).first()
        if existing:
            raise DuplicateNameError(f"A meal named '{existing.name}' already exists.")

    @staticmethod
    def _find_link(
        session: Session, meal_id: int, ingredient_id: int
    ) -> MealIngredient | None:
        return session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id,
            )
        ).first()

    @classmethod
    def _attach_ingredient(
        cls, session: Session, meal_id: int, name: str, qty: float, unit: str
    ) -> None:
        """Shared by add_ingredient and add_from_template.

        Takes the caller's session so the whole operation stays in one
        transaction rather than opening a nested one.
        """
        ingredient = _find_ingredient_by_name(session, name)
        if ingredient is None:
            ingredient = Ingredient(name=name)
            session.add(ingredient)
            session.flush()

        link = cls._find_link(session, meal_id, ingredient.id)
        if link is None:
            session.add(
                MealIngredient(
                    meal_id=meal_id,
                    ingredient_id=ingredient.id,
                    qty=qty,
                    unit=unit,
                )
            )
            return

        if link.unit != unit:
            raise UnitMismatchError(
                f"{name} is already on this meal measured in '{link.unit}'. "
                f"Use the same unit to add more, or remove the existing entry first."
            )
        link.qty = (link.qty or 0) + qty


class WeeklyPlanRepository:
    """Reads and writes the meal assigned to each day of a given week."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get_week(self, week_start_date: date) -> list[WeeklyPlan]:
        """Every stored day for one week. Days never set are simply absent."""
        with self._db.session() as session:
            statement = select(WeeklyPlan).where(
                WeeklyPlan.week_start_date == week_start_date
            )
            return list(session.exec(statement).all())

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
        """Assign several days of one week in a single transaction.

        Saving a whole week a day at a time meant seven sessions and
        fourteen statements - unnoticeable against a local file, several
        seconds against a database across a network. One session handles
        the lot, and either every day lands or none does.

        Args:
            assignments: day -> (meal_id, servings). A meal_id of None
                clears that day.
        """
        if not assignments:
            return

        wanted = {str(day): value for day, value in assignments.items()}

        with self._db.session() as session:
            # Replace rather than read-then-update: a SELECT plus one UPDATE
            # or INSERT per day is eight round trips for a week, where a
            # delete and a bulk insert is two. Row ids are not referenced
            # anywhere, so recreating them costs nothing.
            #
            # Days with no meal still get a row, with meal_id NULL - that is
            # how "explicitly cleared" is distinguished from "never set".
            session.execute(
                delete(WeeklyPlan).where(
                    WeeklyPlan.week_start_date == week_start_date,
                    col(WeeklyPlan.day_of_week).in_(wanted),
                )
            )
            # A Core insert with a list of rows becomes one executemany.
            # Adding ORM objects instead makes SQLAlchemy issue an INSERT per
            # row so it can read back each generated id - ids nothing here
            # needs.
            session.execute(
                insert(WeeklyPlan),
                [
                    {
                        "week_start_date": week_start_date,
                        "day_of_week": day,
                        "meal_id": meal_id,
                        "servings": servings,
                    }
                    for day, (meal_id, servings) in wanted.items()
                ],
            )

    def copy_week(self, source_week: date, target_week: date) -> int:
        """Copy every assigned day from one week onto another.

        Unassigned days in the source are skipped rather than clearing the
        target, so copying never destroys work already done on the target.

        Returns:
            How many days were copied. Zero means the source week was empty.
        """
        copied = 0
        with self._db.session() as session:
            source_plans = session.exec(
                select(WeeklyPlan).where(WeeklyPlan.week_start_date == source_week)
            ).all()

            existing = {
                plan.day_of_week: plan
                for plan in session.exec(
                    select(WeeklyPlan).where(WeeklyPlan.week_start_date == target_week)
                ).all()
            }

            for source in source_plans:
                if source.meal_id is None:
                    continue
                target = existing.get(source.day_of_week)
                if target:
                    target.meal_id = source.meal_id
                    target.servings = source.servings
                else:
                    session.add(
                        WeeklyPlan(
                            week_start_date=target_week,
                            day_of_week=source.day_of_week,
                            meal_id=source.meal_id,
                            servings=source.servings,
                        )
                    )
                copied += 1
        return copied
