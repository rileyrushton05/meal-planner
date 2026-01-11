from sqlmodel import SQLModel, Field, Relationship

from typing import Optional, List

from datetime import datetime

class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    quantity: float
    unit: str  # e.g., "grams", "cups", "ml"
    meal_id: Optional[int] = Field(default=None, foreign_key="meal.id")
    meal: Optional["Meal"] = Relationship(back_populates="ingredients")

class Meal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    servings: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ingredients: List[Ingredient] = Relationship(back_populates="meal")

class GroceryItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    quantity: float
    unit: str
    on_watchlist: bool = False
    notify_on_sale: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)