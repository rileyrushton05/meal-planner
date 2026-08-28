"""Data-access layer.

Each repository takes a :class:`~app.db.Database` and runs every method in
one transaction, so multi-step writes either land completely or not at all.
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
        """Every meal with its ingredients, in two queries rather than one
        per meal - which would be a network round trip each in deployment."""
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
        """One meal and its ingredients. Raises MealNotFoundError."""
        with self._db.session() as session:
            meal = self._get_or_raise(session, meal_id)
            rows = session.exec(
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            ).all()
            return meal, list(rows)

    def add(self, name: str, servings: int = 1) -> Meal:
        """Create a meal. Raises DuplicateNameError if the name is taken."""
        with self._db.session() as session:
            self._assert_name_available(session, name)
            meal = Meal(name=name, servings=servings)
            session.add(meal)
            session.flush()
            return meal

    def add_from_template(self, template: MealTemplate) -> Meal:
        """Create a meal and its template ingredients in one transaction."""
        with self._db.session() as session:
            self._assert_name_available(session, template.name)
            meal = Meal(name=template.name, servings=template.servings)
            session.add(meal)
            session.flush()

            for item in template.ingredients:
                self._attach_ingredient(session, meal.id, item.name, item.qty, item.unit)
            return meal

    def update(self, meal_id: int, name: str, servings: int) -> None:
        """Rename a meal or change its serving size.

        Raises MealNotFoundError, or DuplicateNameError if the name is taken.
        """
        with self._db.session() as session:
            meal = self._get_or_raise(session, meal_id)
            if name.lower() != meal.name.lower():
                self._assert_name_available(session, name, exclude_id=meal_id)
            meal.name = name
            meal.servings = servings

    def delete(self, meal_id: int) -> None:
        """Delete a meal and its ingredient links.

        Days it was planned on are unassigned rather than deleted.
        Raises MealNotFoundError.
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
        """Attach an ingredient, creating it if new.

        Re-adding an existing one accumulates the quantity. Raises
        UnitMismatchError if the meal already uses a different unit.
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
        """Takes the caller's session so the operation stays in one
        transaction rather than opening a nested one."""
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
        """Every stored day for one week. Days never set are absent."""
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

        `assignments` maps day -> (meal_id, servings); a None meal_id clears
        the day. A day at a time meant 14 statements and several seconds
        against a remote database.
        """
        if not assignments:
            return

        wanted = {str(day): value for day, value in assignments.items()}

        with self._db.session() as session:
            # Replace rather than read-then-update: eight round trips for
            # a week becomes two. Row ids are referenced nowhere. Cleared
            # days keep a row with a NULL meal_id, distinguishing them from
            # days never set.
            session.execute(
                delete(WeeklyPlan).where(
                    WeeklyPlan.week_start_date == week_start_date,
                    col(WeeklyPlan.day_of_week).in_(wanted),
                )
            )
            # A Core insert becomes one executemany; adding ORM objects
            # would emit an INSERT per row to read back ids nothing uses.
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
        """Copy assigned days from one week onto another, returning the count.

        Unassigned source days are skipped rather than clearing the target.
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
