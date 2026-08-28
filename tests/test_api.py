"""Tests for the HTTP API.

Exercised through a real ASGI client rather than by calling the handlers,
so routing, validation, serialisation and error mapping are all covered.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.templates import MEAL_TEMPLATES
from server.deps import reset_services_cache
from server.main import app

MONDAY = date(2026, 8, 3)
WEDNESDAY = MONDAY + timedelta(days=2)


@pytest.fixture
def client(db):
    """A client bound to the per-test database.

    The `db` fixture sets MEAL_PLANNER_DB_URL; clearing the cached engine
    makes the API pick it up instead of a previous test's database.
    """
    reset_services_cache()
    with TestClient(app) as test_client:
        yield test_client
    reset_services_cache()


def _create_meal(client, name="Spaghetti", servings=4) -> dict:
    response = client.post("/api/meals", json={"name": name, "servings": servings})
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- meals


def test_health_needs_no_database(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_list_meals(client):
    _create_meal(client, "Spaghetti", 4)

    meals = client.get("/api/meals").json()

    assert [m["name"] for m in meals] == ["Spaghetti"]
    assert meals[0]["servings"] == 4
    assert meals[0]["ingredients"] == []


def test_duplicate_meal_name_is_a_conflict(client):
    _create_meal(client, "Spaghetti")

    response = client.post("/api/meals", json={"name": "spaghetti"})

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_blank_meal_name_is_rejected_before_reaching_the_database(client):
    assert client.post("/api/meals", json={"name": "   "}).status_code == 422


def test_zero_servings_is_rejected(client):
    assert (
        client.post("/api/meals", json={"name": "X", "servings": 0}).status_code == 422
    )


def test_update_meal(client):
    meal = _create_meal(client, "Spaghetti", 4)

    updated = client.patch(
        f"/api/meals/{meal['id']}", json={"name": "Bolognese", "servings": 2}
    ).json()

    assert updated["name"] == "Bolognese"
    assert updated["servings"] == 2


def test_updating_a_missing_meal_is_a_404(client):
    response = client.patch("/api/meals/999", json={"name": "Nope", "servings": 1})

    assert response.status_code == 404


def test_delete_meal(client):
    meal = _create_meal(client)

    assert client.delete(f"/api/meals/{meal['id']}").status_code == 204
    assert client.get("/api/meals").json() == []


# ------------------------------------------------------------- ingredients


def test_add_ingredient_returns_the_updated_meal(client):
    meal = _create_meal(client)

    body = client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 200, "unit": "g"},
    ).json()

    assert len(body["ingredients"]) == 1
    assert body["ingredients"][0]["name"] == "Pasta"
    assert body["ingredients"][0]["qty"] == 200


def test_zero_quantity_ingredient_is_rejected(client):
    meal = _create_meal(client)

    response = client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 0, "unit": "g"},
    )

    assert response.status_code == 422


def test_mismatched_unit_is_a_conflict(client):
    meal = _create_meal(client)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 200, "unit": "g"},
    )

    response = client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 1, "unit": "cup"},
    )

    assert response.status_code == 409
    assert "already on this meal" in response.json()["detail"]


def test_remove_ingredient(client):
    meal = _create_meal(client)
    body = client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 200, "unit": "g"},
    ).json()
    ingredient_id = body["ingredients"][0]["ingredient_id"]

    body = client.delete(f"/api/meals/{meal['id']}/ingredients/{ingredient_id}").json()

    assert body["ingredients"] == []


# -------------------------------------------------------------- templates


def test_create_meal_from_template(client):
    template = MEAL_TEMPLATES[0]

    body = client.post(f"/api/meals/from-template/{template.name}").json()

    assert body["name"] == template.name
    assert {i["name"] for i in body["ingredients"]} == {
        i.name for i in template.ingredients
    }


def test_unknown_template_is_a_404(client):
    assert client.post("/api/meals/from-template/Nonexistent").status_code == 404


# ------------------------------------------------------------------- plan


def test_any_date_in_a_week_resolves_to_its_monday(client):
    body = client.get(f"/api/plan/{WEDNESDAY.isoformat()}").json()

    assert body["week_start"] == MONDAY.isoformat()


def test_set_and_read_back_a_week(client):
    meal = _create_meal(client)

    body = client.put(
        f"/api/plan/{MONDAY.isoformat()}",
        json={
            "days": [
                {"day": "Monday", "meal_id": meal["id"], "servings": 2},
                {"day": "Tuesday", "meal_id": None, "servings": None},
            ]
        },
    ).json()

    by_day = {d["day"]: d for d in body["days"]}
    assert by_day["Monday"]["meal_id"] == meal["id"]
    assert by_day["Monday"]["servings"] == 2
    assert by_day["Tuesday"]["meal_id"] is None


def test_copy_previous_week(client):
    meal = _create_meal(client)
    previous = MONDAY - timedelta(days=7)
    client.put(
        f"/api/plan/{previous.isoformat()}",
        json={"days": [{"day": "Monday", "meal_id": meal["id"], "servings": 3}]},
    )

    body = client.post(f"/api/plan/{MONDAY.isoformat()}/copy-previous").json()

    by_day = {d["day"]: d for d in body["days"]}
    assert by_day["Monday"]["meal_id"] == meal["id"]
    assert by_day["Monday"]["servings"] == 3


# ---------------------------------------------------------- grocery list


def test_grocery_list_scales_and_merges(client):
    meal = _create_meal(client, "Spaghetti", servings=4)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 400, "unit": "g"},
    )
    client.put(
        f"/api/plan/{MONDAY.isoformat()}",
        json={"days": [{"day": "Monday", "meal_id": meal["id"], "servings": 2}]},
    )

    lines = client.get(f"/api/grocery-list/{MONDAY.isoformat()}").json()

    assert len(lines) == 1
    assert lines[0]["name"] == "Pasta"
    assert lines[0]["qty"] == 200  # half the recipe
    assert lines[0]["display"] == "200 g"


# ------------------------------------------------------------------ state


def test_state_returns_everything_in_one_response(client):
    meal = _create_meal(client)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 200, "unit": "g"},
    )
    client.put(
        f"/api/plan/{MONDAY.isoformat()}",
        json={"days": [{"day": "Monday", "meal_id": meal["id"], "servings": 4}]},
    )

    body = client.get(f"/api/state?week={WEDNESDAY.isoformat()}").json()

    assert body["week_start"] == MONDAY.isoformat()
    assert [m["name"] for m in body["meals"]] == ["Spaghetti"]
    assert body["meals"][0]["ingredients"][0]["name"] == "Pasta"
    assert body["ingredient_names"] == ["Pasta"]
    assert {d["day"] for d in body["plan"]} == {"Monday"}
    assert len(body["templates"]) == len(MEAL_TEMPLATES)


def test_state_defaults_to_the_current_week(client):
    body = client.get("/api/state").json()

    today = date.today()
    assert body["week_start"] == (today - timedelta(days=today.weekday())).isoformat()


# ------------------------------------------------- missing meal handling


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/meals/999/ingredients", {"name": "X", "qty": 1, "unit": "g"}),
        ("patch", "/api/meals/999/ingredients/1", {"qty": 5, "unit": "g"}),
        ("delete", "/api/meals/999/ingredients/1", None),
        ("delete", "/api/meals/999", None),
    ],
)
def test_operations_on_a_missing_meal_return_404(client, method, path, body):
    """Regression test: these handlers scanned every meal and picked one with
    a bare next(), which raised StopIteration for an unknown id and surfaced
    as a 500 rather than a 404."""
    response = getattr(client, method)(path, **({"json": body} if body else {}))

    assert response.status_code == 404
    assert "detail" in response.json()


def test_changing_an_ingredient_not_on_the_meal_is_404(client):
    """The meal exists but the ingredient is not attached to it.

    Both handlers used to return 200 having changed nothing, so a client
    could not tell a successful edit from one that silently did not happen.
    """
    meal = _create_meal(client)

    response = client.patch(
        f"/api/meals/{meal['id']}/ingredients/999", json={"qty": 5, "unit": "g"}
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_removing_an_ingredient_not_on_the_meal_is_404(client):
    meal = _create_meal(client)

    response = client.delete(f"/api/meals/{meal['id']}/ingredients/999")

    assert response.status_code == 404


@pytest.mark.parametrize("day", ["Funday", "monday ", "", "1"])
def test_a_day_that_is_not_a_weekday_is_rejected(client, day):
    """Unvalidated, these were written straight into the plan table, leaving
    rows no client knows how to render."""
    response = client.put(
        f"/api/plan/{MONDAY}", json={"days": [{"day": day, "meal_id": None}]}
    )

    assert response.status_code == 422
    assert client.get(f"/api/plan/{MONDAY}").json()["days"] == []
