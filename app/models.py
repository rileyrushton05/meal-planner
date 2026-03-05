from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime, UTC


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


class GroceryItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    desired_qty: Optional[float] = None
    unit: Optional[str] = None
    bought: bool = False

class WeeklyPlan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    day_of_week: str = Field(index=True)
    meal_id: Optional[int] = Field(default=None, foreign_key="meal.id")