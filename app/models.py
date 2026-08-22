from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime, date, UTC


class MealIngredient(SQLModel, table=True):
    meal_id: Optional[int] = Field(default=None, foreign_key="meal.id", primary_key=True)
    ingredient_id: Optional[int] = Field(default=None, foreign_key="ingredient.id", primary_key=True)

    qty: Optional[float] = None
    unit: Optional[str] = None


class Meal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    servings: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    ingredients: List["Ingredient"] = Relationship(
        back_populates="meals", link_model=MealIngredient
    )


class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    meals: List[Meal] = Relationship(
        back_populates="ingredients", link_model=MealIngredient
    )


class WeeklyPlan(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("week_start_date", "day_of_week", name="uq_weeklyplan_week_day"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    week_start_date: date = Field(index=True)
    day_of_week: str = Field(index=True)
    meal_id: Optional[int] = Field(default=None, foreign_key="meal.id")
    # Servings actually planned for this day, which may differ from the
    # meal's own base servings (e.g. cooking a serves-4 recipe for 2
    # people). None means "use the meal's base servings unscaled".
    servings: Optional[int] = None