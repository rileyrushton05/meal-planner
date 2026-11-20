"""What the ingredient field suggests as a person types, and the unit it
fills in when they pick one.

A person's own ingredients come first, with the unit they usually measure
each in. Catalogue items they have not used yet are suggested too, with the
unit the built-in templates measure them in, failing that the catalogue's
own (a teaspoon of salt), and failing that the natural one for how the item
is measured (grams, millilitres, or a plain count).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType

from app.catalog import CatalogEntry, catalog_key, load_catalog
from app.models import Measure
from app.parsing import canonical_unit
from app.templates import MEAL_TEMPLATES, MealTemplate

_BY_MEASURE = {Measure.MASS: "g", Measure.VOLUME: "ml", Measure.COUNT: ""}


@dataclass(frozen=True, slots=True)
class Suggestion:
    name: str
    #: The unit to fill in: "" for a plain count.
    unit: str


def ingredient_suggestions(
    names: Iterable[str], lines: Iterable[tuple[str, str]]
) -> list[Suggestion]:
    """Suggestions for one person, sorted by name.

    `names` is every ingredient they have; `lines` is (ingredient name,
    unit) for every ingredient on their meals.
    """
    catalogue = _catalogue()
    units: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for name, unit in lines:
        units[catalog_key(name)][canonical_unit(unit)] += 1

    suggestions: dict[str, Suggestion] = {}
    covered: set[str] = set()
    for name in names:
        key = catalog_key(name)
        entry = catalogue.get(key)
        if entry:
            covered.add(entry.name_key)
        if units[key]:
            # The commonest; on a tie, the one met first.
            unit = units[key].most_common(1)[0][0]
        else:
            unit = _usual_units()[entry.name_key] if entry else ""
        suggestions[key] = Suggestion(name, unit)

    for key, unit in _usual_units().items():
        if key not in covered and key not in suggestions:
            suggestions[key] = Suggestion(catalogue[key].name, unit)

    return sorted(suggestions.values(), key=lambda s: s.name.casefold())


@cache
def _catalogue() -> Mapping[str, CatalogEntry]:
    """Every catalogue spelling -> its entry."""
    return MappingProxyType(
        {key: entry for entry in load_catalog() for key in entry.keys}
    )


def usual_units(
    entries: Iterable[CatalogEntry], templates: Iterable[MealTemplate]
) -> dict[str, str]:
    """Each catalogue item's name key -> the unit to suggest for it: the one
    the templates use most, else the catalogue's own (`unit`), else the
    natural one for how it is measured."""
    entries = list(entries)
    owner = {key: entry for entry in entries for key in entry.keys}
    in_templates: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for template in templates:
        for item in template.ingredients:
            entry = owner.get(catalog_key(item.name))
            if entry:
                in_templates[entry.name_key][canonical_unit(item.unit)] += 1

    return {
        entry.name_key: (
            in_templates[entry.name_key].most_common(1)[0][0]
            if in_templates[entry.name_key]
            else entry.unit
            if entry.unit is not None
            else _BY_MEASURE[entry.measure]
        )
        for entry in entries
    }


@cache
def _usual_units() -> Mapping[str, str]:
    return MappingProxyType(usual_units(load_catalog(), MEAL_TEMPLATES))
