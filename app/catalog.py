"""The ingredient catalogue: common grocery items that a person's own
ingredients link to, so they can be grouped by aisle and, later, priced.

The catalogue is reference data kept in the repository, in `catalog.csv`
beside this module: one row per item, with every other spelling of it in
`aliases`. A change to it is a reviewable diff. `python -m app.jobs
sync-catalog` loads it, idempotently, and relinks every ingredient.

Matching is deliberately literal: an ingredient links when its name, with
case and spacing ignored (`catalog_key`), is an item's name or one of its
aliases. No guessing at plurals or typos, so a link is never wrong in a way
nobody chose; a spelling worth matching is added as an alias instead.

The planning here is pure, so it is tested without a database; the
repository (`CatalogRepository`) applies the plan.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.models import Category, Measure

CATALOG_PATH = Path(__file__).with_name("catalog.csv")
_COLUMNS = ["name", "category", "measure", "each_grams", "aliases"]


def catalog_key(name: str) -> str:
    """How a name is compared: case and spacing ignored."""
    return " ".join(name.casefold().split())


class CatalogError(ValueError):
    """The catalogue file is malformed; the message names the line."""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    name: str
    category: Category
    measure: Measure
    each_grams: int | None
    #: Every key that means this item, its own name's first.
    keys: tuple[str, ...]

    @property
    def name_key(self) -> str:
        return self.keys[0]


def load_catalog(path: Path | None = None) -> list[CatalogEntry]:
    """Read and check the catalogue (`CATALOG_PATH` unless told otherwise).
    Raises CatalogError, naming the line, for anything that would load
    wrongly: an unknown category or measure, a bad weight, or a spelling
    that means two items."""
    path = path or CATALOG_PATH
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != _COLUMNS:
            raise CatalogError(
                f"{path.name}: the columns must be {', '.join(_COLUMNS)}."
            )
        entries = [_entry(row, reader.line_num, path.name) for row in reader]

    owner: dict[str, str] = {}
    for entry in entries:
        for key in entry.keys:
            if key in owner:
                raise CatalogError(
                    f"{path.name}: '{key}' means both {owner[key]} and {entry.name}."
                )
            owner[key] = entry.name
    return entries


def _entry(row: dict[str, str], line: int, file: str) -> CatalogEntry:
    where = f"{file}, line {line}"
    name = row["name"].strip()
    if not name:
        raise CatalogError(f"{where}: the name is empty.")
    try:
        category = Category(row["category"].strip())
        measure = Measure(row["measure"].strip())
    except ValueError as error:
        raise CatalogError(f"{where}: {error}.") from None
    each = row["each_grams"].strip()
    if each and not (each.isdigit() and int(each) > 0):
        raise CatalogError(f"{where}: each_grams must be a whole number above 0.")
    if measure is Measure.COUNT and not each:
        # Counted items need a weight to be priced by the kilo or compared.
        raise CatalogError(f"{where}: a counted item needs each_grams.")
    aliases = [
        catalog_key(alias) for alias in row["aliases"].split("|") if alias.strip()
    ]
    keys = [catalog_key(name), *aliases]
    if len(set(keys)) != len(keys):
        raise CatalogError(f"{where}: a spelling is listed twice.")
    return CatalogEntry(
        name, category, measure, int(each) if each else None, tuple(keys)
    )


# --- Syncing -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredItem:
    id: int
    name: str
    name_key: str
    category: str
    measure: str
    each_grams: int | None


@dataclass(frozen=True, slots=True)
class StoredIngredient:
    id: int
    name: str
    catalog_item_id: int | None


@dataclass(slots=True)
class SyncPlan:
    """What a sync changes. Items are named by key, because new ones have no
    id until they are inserted."""

    add: list[CatalogEntry] = field(default_factory=list)
    update: list[CatalogEntry] = field(default_factory=list)
    remove: list[int] = field(default_factory=list)
    #: alias key -> item name key, for every alias the catalogue should hold.
    aliases: dict[str, str] = field(default_factory=dict)
    #: Ingredients whose link changes: ingredient id -> item name key, or
    #: None to unlink.
    relink: dict[int, str | None] = field(default_factory=dict)
    #: Names no item matched, for adding aliases (counted, never logged).
    unmatched: list[str] = field(default_factory=list)


def plan_sync(
    entries: Iterable[CatalogEntry],
    items: Iterable[StoredItem],
    ingredients: Iterable[StoredIngredient],
) -> SyncPlan:
    plan = SyncPlan()
    stored = {item.name_key: item for item in items}
    wanted = {entry.name_key: entry for entry in entries}

    for key, entry in wanted.items():
        item = stored.get(key)
        if item is None:
            plan.add.append(entry)
        elif (item.name, item.category, item.measure, item.each_grams) != (
            entry.name,
            entry.category.value,
            entry.measure.value,
            entry.each_grams,
        ):
            plan.update.append(entry)
    plan.remove = sorted(item.id for key, item in stored.items() if key not in wanted)

    plan.aliases = {
        alias: entry.name_key for entry in wanted.values() for alias in entry.keys
    }
    key_of_id: Mapping[int, str] = {item.id: key for key, item in stored.items()}
    for ingredient in ingredients:
        target = plan.aliases.get(catalog_key(ingredient.name))
        current = (
            key_of_id.get(ingredient.catalog_item_id)
            if ingredient.catalog_item_id
            else None
        )
        if target != current:
            plan.relink[ingredient.id] = target
        if target is None:
            plan.unmatched.append(ingredient.name)
    return plan
