"""The ingredient catalogue: the file in the repository, how it is loaded,
and how a person's ingredients are linked to it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from api_client import api_client
from sqlalchemy import func, text
from sqlmodel import select

from app import catalog, jobs
from app.catalog import (
    CatalogError,
    StoredIngredient,
    StoredItem,
    catalog_key,
    load_catalog,
    plan_sync,
)
from app.db import Database
from app.models import CatalogAlias, CatalogItem, Category, Measure
from app.repositories import MealRepository, UserRepository
from app.templates import MEAL_TEMPLATES

NOW = datetime(2026, 11, 19, tzinfo=UTC)
HEADER = "name,category,measure,each_grams,aliases,unit\n"


def _write(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "catalog.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def _sync(*, dry_run: bool = False, db: Database) -> jobs.CatalogSynced:
    with db.transaction() as session:
        return jobs.sync_catalog(session, now=NOW, dry_run=dry_run)


def _ingredient(db: Database, name: str) -> int:
    """An ingredient on a meal of a new user; returns the user's id."""
    with db.transaction() as session:
        user = UserRepository(session).create(is_guest=True)
        user_id = user.id or 0
        meals = MealRepository(session, user_id=user_id)
        meal = meals.add(f"Meal {user_id}")
        meals.add_ingredient(meal.id or 0, name, 1, "")
    return user_id


def _linked_item(db: Database, name: str) -> str | None:
    """The catalogue item an ingredient of that name is linked to."""
    with db.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT c.name FROM ingredients i "
                "LEFT JOIN catalog_items c ON c.id = i.catalog_item_id "
                "WHERE i.name = :name"
            ),
            {"name": name},
        ).scalar_one()


# --- The file ------------------------------------------------------------------


def test_names_are_compared_ignoring_case_and_spacing() -> None:
    assert catalog_key("  Beef   MINCE ") == "beef mince"


def test_the_catalogue_in_the_repository_loads() -> None:
    entries = load_catalog()

    assert len(entries) >= 60
    assert {entry.category for entry in entries} == set(Category)
    assert {entry.measure for entry in entries} == set(Measure)


def test_every_template_ingredient_is_a_catalogue_item_by_name() -> None:
    """Templates are written in catalogue names, so a meal added from one
    is linked in full."""
    names = {entry.name for entry in load_catalog()}
    missing = {
        ingredient.name
        for template in MEAL_TEMPLATES
        for ingredient in template.ingredients
        if ingredient.name not in names
    }
    assert missing == set()


@pytest.mark.parametrize(
    ("rows", "complaint"),
    [
        ("Onion,aisle-nine,count,150,\n", "line 2"),
        ("Onion,produce,handful,150,\n", "line 2"),
        ("Onion,produce,count,,\n", "needs each_grams"),
        ("Onion,produce,count,-5,\n", "whole number above 0"),
        (",produce,mass,,\n", "name is empty"),
        ("Onion,produce,count,150,onions|Onions\n", "listed twice"),
        ("Salt,pantry,mass,,,teaspoon\n", "as the app does: 'tsp'"),
        (
            "Onion,produce,count,150,shallot\nShallot,produce,count,30,\n",
            "'shallot' means both Onion and Shallot",
        ),
    ],
    ids=[
        "unknown category",
        "unknown measure",
        "count without a weight",
        "negative weight",
        "no name",
        "spelling twice in a row",
        "a unit spelled its own way",
        "spelling for two items",
    ],
)
def test_a_broken_catalogue_is_refused_naming_the_problem(
    tmp_path, rows, complaint
) -> None:
    with pytest.raises(CatalogError, match=complaint):
        load_catalog(_write(tmp_path, rows))


def test_the_columns_are_checked(tmp_path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text("name,aisle\nOnion,produce\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="columns must be"):
        load_catalog(path)


# --- Planning ------------------------------------------------------------------


def test_a_plan_adds_updates_removes_and_relinks(tmp_path) -> None:
    entries = load_catalog(
        _write(
            tmp_path,
            "Onion,produce,count,150,onions\nGarlic,produce,count,5,garlic cloves\n",
        )
    )
    items = [
        StoredItem(1, "Onion", "onion", "pantry", "count", 150),  # moved aisle
        StoredItem(2, "Leek", "leek", "produce", "count", 200),  # dropped
    ]
    ingredients = [
        StoredIngredient(10, "ONIONS", None),  # newly matched
        StoredIngredient(11, "leek", 2),  # its item is going
        StoredIngredient(12, "Dragon fruit", None),  # matches nothing
        StoredIngredient(13, "onion", 1),  # already right
    ]

    plan = plan_sync(entries, items, ingredients)

    assert [entry.name for entry in plan.add] == ["Garlic"]
    assert [entry.name for entry in plan.update] == ["Onion"]
    assert plan.remove == [2]
    assert plan.aliases == {
        "onion": "onion",
        "onions": "onion",
        "garlic": "garlic",
        "garlic cloves": "garlic",
    }
    assert plan.relink == {10: "onion", 11: None}
    assert sorted(plan.unmatched) == ["Dragon fruit", "leek"]


# --- Syncing a database --------------------------------------------------------


def test_syncing_loads_everything_and_a_second_run_changes_nothing(db) -> None:
    first = _sync(db=db)
    second = _sync(db=db)

    entries = load_catalog()
    assert first.added == len(entries)
    assert second == jobs.CatalogSynced(0, 0, 0, 0, 0, 0)
    with db.transaction() as session:
        aliases = session.exec(select(func.count()).select_from(CatalogAlias)).one()
    assert aliases == sum(len(entry.keys) for entry in entries)


def test_a_dry_run_counts_and_changes_nothing(db) -> None:
    result = _sync(db=db, dry_run=True)

    assert result.added == len(load_catalog())
    with db.transaction() as session:
        assert session.exec(select(func.count()).select_from(CatalogItem)).one() == 0


def test_existing_ingredients_are_linked_by_name_or_alias(db) -> None:
    _ingredient(db, "Brown Onions")
    _ingredient(db, "dragon fruit")

    result = _sync(db=db)

    assert _linked_item(db, "Brown Onions") == "Onion"
    assert _linked_item(db, "dragon fruit") is None
    assert result.linked == 1
    assert result.unmatched_names == ("dragon fruit",)


def test_a_new_ingredient_is_linked_as_it_is_created(db) -> None:
    _sync(db=db)

    with api_client() as client:
        meal = client.post(
            "/api/meals", json={"name": "Spag Bol", "servings": 4}
        ).json()
        added = client.post(
            f"/api/meals/{meal['id']}/ingredients",
            json={"name": "spaghetti", "qty": 400, "unit": "g"},
        )
        assert added.status_code == 200, added.text

    assert _linked_item(db, "spaghetti") == "Pasta"


def test_a_meal_from_a_template_is_linked_in_full(db) -> None:
    _sync(db=db)

    with api_client() as client:
        response = client.post("/api/meals/from-template/Pad Thai")
        assert response.status_code == 201, response.text

    with db.engine.connect() as connection:
        linked, unlinked = connection.execute(
            text(
                "SELECT count(catalog_item_id), count(*) - count(catalog_item_id) "
                "FROM ingredients"
            )
        ).one()
    assert (linked, unlinked) == (7, 0)


def test_an_item_dropped_from_the_catalogue_unlinks_without_deleting(
    db, tmp_path, monkeypatch
) -> None:
    _ingredient(db, "Leek")
    monkeypatch.setattr(
        catalog, "CATALOG_PATH", _write(tmp_path, "Leek,produce,count,200,\n")
    )
    _sync(db=db)
    assert _linked_item(db, "Leek") == "Leek"

    monkeypatch.setattr(
        catalog, "CATALOG_PATH", _write(tmp_path, "Onion,produce,count,150,\n")
    )
    result = _sync(db=db)

    assert result.removed == 1
    assert result.unlinked == 1
    assert _linked_item(db, "Leek") is None


def test_the_command_line_reports_counts_and_never_names_by_default(db, capsys) -> None:
    _ingredient(db, "Grandma's secret sauce")

    assert jobs.main(["sync-catalog"], now=NOW) == 0

    output = capsys.readouterr().out
    assert f"Synced: {len(load_catalog())} added" in output
    assert "1 unmatched" in output
    # Users' own words: only shown when asked for, on a local run.
    assert "secret sauce" not in output

    jobs.main(["sync-catalog", "--dry-run", "--show-unmatched"], now=NOW)
    assert "not in the catalogue: Grandma's secret sauce" in capsys.readouterr().out
