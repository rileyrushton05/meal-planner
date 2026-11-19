"""What the ingredient field suggests (app/suggestions.py)."""

from __future__ import annotations

from app.catalog import CatalogEntry, load_catalog
from app.models import Category, Measure
from app.suggestions import Suggestion, ingredient_suggestions, usual_units
from app.templates import MealTemplate, TemplateIngredient


def make_template(name: str, *lines: tuple[str, float, str]) -> MealTemplate:
    return MealTemplate(name, 2, tuple(TemplateIngredient(*line) for line in lines))


def _units(names=(), lines=()) -> dict[str, str]:
    return {s.name: s.unit for s in ingredient_suggestions(names, lines)}


def test_with_nothing_of_their_own_every_catalogue_item_is_offered() -> None:
    offered = _units()

    assert set(offered) == {entry.name for entry in load_catalog()}


def test_catalogue_items_come_with_the_unit_the_templates_use() -> None:
    offered = _units()

    assert offered["Garlic"] == "cloves"
    assert offered["Beef Mince"] == "g"
    assert offered["Onion"] == ""


def test_an_item_no_template_uses_gets_the_unit_for_how_it_is_measured() -> None:
    entries = [
        CatalogEntry("Sumac", Category.PANTRY, Measure.MASS, None, ("sumac",)),
        CatalogEntry("Mirin", Category.PANTRY, Measure.VOLUME, None, ("mirin",)),
        CatalogEntry("Lime", Category.PRODUCE, Measure.COUNT, 60, ("lime", "limes")),
    ]
    template = make_template("Fish", ("limes", 2, ""))

    assert usual_units(entries, []) == {"sumac": "g", "mirin": "ml", "lime": ""}
    assert usual_units(entries, [template])["lime"] == ""


def test_the_unit_templates_use_most_is_the_one_suggested() -> None:
    entries = [CatalogEntry("Rice", Category.PANTRY, Measure.MASS, None, ("rice",))]
    templates = [
        make_template("A", ("Rice", 1, "cup")),
        make_template("B", ("Rice", 2, "cups")),
        make_template("C", ("Rice", 200, "g")),
    ]

    assert usual_units(entries, templates) == {"rice": "cups"}


def test_their_own_unit_wins_over_the_catalogues() -> None:
    offered = _units(["Garlic"], [("Garlic", "tsp"), ("Garlic", "tsp"), ("garlic", "")])

    assert offered["Garlic"] == "tsp"


def test_their_unit_is_compared_as_the_app_spells_it() -> None:
    offered = _units(["Rice"], [("Rice", "cup"), ("Rice", "cups"), ("Rice", "g")])

    assert offered["Rice"] == "cups"


def test_an_ingredient_on_no_meal_falls_back_to_the_catalogue() -> None:
    assert _units(["garlic"])["garlic"] == "cloves"


def test_their_own_name_replaces_the_catalogue_item_it_is() -> None:
    """Someone who writes "onions" is offered "onions", not "Onion" as well."""
    offered = _units(["onions"], [("onions", "")])

    assert "onions" in offered
    assert "Onion" not in offered


def test_names_outside_the_catalogue_are_offered_with_their_unit() -> None:
    suggestions = ingredient_suggestions(
        ["Smoked Paprika", "Sumac"], [("Smoked Paprika", "tsp")]
    )

    assert Suggestion("Smoked Paprika", "tsp") in suggestions
    assert Suggestion("Sumac", "") in suggestions


def test_suggestions_are_in_alphabetical_order_ignoring_case() -> None:
    names = [s.name for s in ingredient_suggestions(["apricots", "Zest"], [])]

    assert names == sorted(names, key=str.casefold)
