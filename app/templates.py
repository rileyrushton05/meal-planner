"""Starter meals offered by the Quick Add gallery.

Hand-curated rather than generated, so the quantities stay realistic. Adding
a meal here is the only step needed for it to appear in the UI.
"""

from __future__ import annotations

from typing import NamedTuple


class TemplateIngredient(NamedTuple):
    """One line of a template's ingredient list."""

    name: str
    qty: float
    #: Empty for count-based items ("1 onion", "3 eggs"), which have no
    #: meaningful unit of measurement.
    unit: str = ""


class MealTemplate(NamedTuple):
    """A ready-made meal a user can add in one click."""

    name: str
    servings: int
    ingredients: tuple[TemplateIngredient, ...]

    @property
    def ingredient_summary(self) -> str:
        """Comma-separated ingredient names, for the gallery card."""
        return ", ".join(item.name for item in self.ingredients)


def _template(name: str, servings: int, *ingredients: tuple) -> MealTemplate:
    """Build a MealTemplate from terse (name, qty, unit) tuples."""
    return MealTemplate(
        name=name,
        servings=servings,
        ingredients=tuple(TemplateIngredient(*item) for item in ingredients),
    )


MEAL_TEMPLATES: tuple[MealTemplate, ...] = (
    _template(
        "Spaghetti Bolognese", 4,
        ("Pasta", 400, "g"),
        ("Beef Mince", 500, "g"),
        ("Tomato Passata", 700, "g"),
        ("Onion", 1),
        ("Garlic", 2, "cloves"),
    ),
    _template(
        "Chicken Stir Fry", 4,
        ("Chicken Breast", 500, "g"),
        ("Mixed Vegetables", 400, "g"),
        ("Soy Sauce", 60, "ml"),
        ("Rice", 300, "g"),
        ("Garlic", 2, "cloves"),
    ),
    _template(
        "Tacos", 4,
        ("Beef Mince", 500, "g"),
        ("Taco Shells", 8),
        ("Cheese", 150, "g"),
        ("Lettuce", 1),
        ("Tomato", 2),
        ("Sour Cream", 200, "g"),
    ),
    _template(
        "Butter Chicken", 4,
        ("Chicken Thigh", 600, "g"),
        ("Butter Chicken Sauce", 500, "ml"),
        ("Rice", 300, "g"),
        ("Naan", 4),
    ),
    _template(
        "Fried Rice", 4,
        ("Rice", 400, "g"),
        ("Eggs", 3),
        ("Frozen Peas", 150, "g"),
        ("Soy Sauce", 40, "ml"),
        ("Spring Onion", 2),
    ),
    _template(
        "Roast Chicken", 4,
        ("Whole Chicken", 1.5, "kg"),
        ("Potatoes", 800, "g"),
        ("Carrots", 400, "g"),
        ("Olive Oil", 30, "ml"),
    ),
    _template(
        "Chicken Curry", 4,
        ("Chicken Thigh", 600, "g"),
        ("Curry Paste", 100, "g"),
        ("Coconut Milk", 400, "ml"),
        ("Rice", 300, "g"),
    ),
    _template(
        "Caesar Salad", 2,
        ("Cos Lettuce", 1),
        ("Chicken Breast", 300, "g"),
        ("Parmesan", 50, "g"),
        ("Croutons", 100, "g"),
        ("Caesar Dressing", 100, "ml"),
    ),
    _template(
        "Fish and Chips", 2,
        ("Fish Fillets", 400, "g"),
        ("Potatoes", 600, "g"),
        ("Flour", 100, "g"),
        ("Frozen Peas", 200, "g"),
    ),
    _template(
        "Vegetable Soup", 4,
        ("Mixed Vegetables", 600, "g"),
        ("Vegetable Stock", 1000, "ml"),
        ("Onion", 1),
        ("Garlic", 2, "cloves"),
    ),
    _template(
        "Omelette", 1,
        ("Eggs", 3),
        ("Cheese", 50, "g"),
        ("Milk", 30, "ml"),
    ),
    _template(
        "BLT Sandwich", 2,
        ("Bacon", 150, "g"),
        ("Lettuce", 1),
        ("Tomato", 2),
        ("Bread", 4, "slices"),
    ),
    _template(
        "Pasta Carbonara", 4,
        ("Pasta", 400, "g"),
        ("Bacon", 200, "g"),
        ("Eggs", 3),
        ("Parmesan", 80, "g"),
    ),
    _template(
        "Beef Burgers", 4,
        ("Beef Mince", 500, "g"),
        ("Burger Buns", 4),
        ("Cheese", 4, "slices"),
        ("Lettuce", 1),
        ("Tomato", 1),
    ),
    _template(
        "Vegetable Curry", 4,
        ("Mixed Vegetables", 600, "g"),
        ("Curry Paste", 100, "g"),
        ("Coconut Milk", 400, "ml"),
        ("Rice", 300, "g"),
    ),
    _template(
        "Chicken Schnitzel", 4,
        ("Chicken Breast", 600, "g"),
        ("Breadcrumbs", 150, "g"),
        ("Eggs", 2),
        ("Flour", 100, "g"),
    ),
    _template(
        "Beef Stir Fry", 4,
        ("Beef Strips", 500, "g"),
        ("Mixed Vegetables", 400, "g"),
        ("Soy Sauce", 60, "ml"),
        ("Rice", 300, "g"),
        ("Garlic", 2, "cloves"),
    ),
    _template(
        "Pancakes", 4,
        ("Flour", 300, "g"),
        ("Eggs", 2),
        ("Milk", 400, "ml"),
        ("Butter", 30, "g"),
    ),
)
