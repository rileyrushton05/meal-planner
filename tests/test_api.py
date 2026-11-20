"""Tests for the HTTP API.

Exercised through a real ASGI client rather than by calling the handlers,
so routing, validation, serialisation and error mapping are all covered.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from api_client import api_client

from app.templates import MEAL_TEMPLATES

MONDAY = date(2026, 8, 3)
WEDNESDAY = MONDAY + timedelta(days=2)


@pytest.fixture
def client(db):
    """A guest's client, bound to the per-test database."""
    with api_client() as test_client:
        yield test_client


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


def test_units_are_stored_as_the_app_spells_them(client):
    """So that "1 clove" and "2 cloves" of the same thing add up."""
    meal = _create_meal(client)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Garlic", "qty": 1, "unit": "clove"},
    )

    body = client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Garlic", "qty": 2, "unit": "Cloves"},
    ).json()

    assert _amounts(body) == [("Garlic", 3, "cloves")]


# ------------------------------------------------ replacing the whole list


def _amounts(meal: dict) -> list[tuple[str, float, str]]:
    return sorted((i["name"], i["qty"], i["unit"]) for i in meal["ingredients"])


def _replace(client, meal_id: int, *lines: tuple[str, float, str]):
    return client.put(
        f"/api/meals/{meal_id}/ingredients",
        json={
            "ingredients": [
                {"name": name, "qty": qty, "unit": unit} for name, qty, unit in lines
            ]
        },
    )


def test_replacing_the_ingredients_sets_exactly_the_list_sent(client):
    meal = _create_meal(client)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Pasta", "qty": 200, "unit": "g"},
    )

    response = _replace(
        client,
        meal["id"],
        ("Beef Mince", 500, "g"),
        ("Onion", 2, ""),
        ("Pasta", 1, "kg"),
    )

    assert response.status_code == 200, response.text
    assert _amounts(response.json()) == [
        ("Beef Mince", 500, "g"),
        ("Onion", 2, ""),
        ("Pasta", 1, "kg"),
    ]
    assert _amounts(client.get(f"/api/meals/{meal['id']}").json()) == _amounts(
        response.json()
    )


def test_replacing_with_nothing_empties_the_meal(client):
    meal = _create_meal(client)
    _replace(client, meal["id"], ("Pasta", 200, "g"))

    assert _replace(client, meal["id"]).json()["ingredients"] == []


def test_the_same_ingredient_twice_in_one_unit_adds_up(client):
    meal = _create_meal(client)

    body = _replace(client, meal["id"], ("Butter", 50, "g"), ("butter", 20, "g")).json()

    assert _amounts(body) == [("Butter", 70, "g")]


def test_a_list_that_cannot_be_saved_leaves_the_old_one(client):
    """One transaction: the conflict on the last line undoes the delete and
    the inserts before it."""
    meal = _create_meal(client)
    _replace(client, meal["id"], ("Pasta", 200, "g"))

    response = _replace(
        client, meal["id"], ("Onion", 2, ""), ("Butter", 50, "g"), ("Butter", 1, "tbsp")
    )

    assert response.status_code == 409
    assert response.json()["type"].endswith("unit-mismatch")
    assert _amounts(client.get(f"/api/meals/{meal['id']}").json()) == [
        ("Pasta", 200, "g")
    ]


def test_a_list_is_saved_in_one_request_however_long(client):
    meal = _create_meal(client)
    lines = [(f"Thing {n}", n, "g") for n in range(1, 101)]

    assert _replace(client, meal["id"], *lines).status_code == 200
    assert _replace(
        client, meal["id"], *lines, ("One too many", 1, "g")
    ).status_code == (422)


def test_every_line_of_a_list_is_checked(client):
    meal = _create_meal(client)

    response = _replace(client, meal["id"], ("Onion", 2, ""), ("Salt", 0, "g"))

    assert response.status_code == 422


# ---------------------------------------------------- reading pasted lines


def test_pasted_lines_are_read_for_a_preview(client):
    body = client.post(
        "/api/ingredients/parse",
        json={"text": "500g beef mince\n\nFor the sauce:\n2-3 garlic cloves, crushed"},
    ).json()

    assert body["lines"] == [
        {
            "text": "500g beef mince",
            "qty": 500,
            "unit": "g",
            "name": "Beef Mince",
            "prep": "",
            "catalog_item": "Beef Mince",
            "confidence": "high",
            "warnings": [],
        },
        {
            "text": "2-3 garlic cloves, crushed",
            "qty": 3,
            "unit": "cloves",
            "name": "Garlic",
            "prep": "crushed",
            "catalog_item": "Garlic",
            "confidence": "medium",
            "warnings": ["Read 2 to 3 as 3."],
        },
    ]


def test_reading_lines_saves_nothing(client):
    client.post("/api/ingredients/parse", json={"text": "500g beef mince"})

    assert client.get("/api/meals").json() == []
    names = {
        s["name"] for s in client.get("/api/state").json()["ingredient_suggestions"]
    }
    assert "500g beef mince" not in names


def test_a_line_with_no_amount_comes_back_unsure(client):
    (line,) = client.post(
        "/api/ingredients/parse", json={"text": "Salt to taste"}
    ).json()["lines"]

    assert (line["qty"], line["confidence"]) == (None, "low")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("\n".join(["1 onion"] * 101), "Paste up to 100 lines at a time."),
        ("1 onion\n" + "x" * 201, "Line 2 is longer than 200 characters."),
    ],
    ids=["too many lines", "a line too long"],
)
def test_reading_is_bounded(client, text, message):
    response = client.post("/api/ingredients/parse", json={"text": text})

    assert response.status_code == 422
    assert message in response.text


def test_a_hundred_lines_with_blank_ones_between_are_allowed(client):
    text = "\n\n".join(["1 onion"] * 100)

    response = client.post("/api/ingredients/parse", json={"text": text})

    assert response.status_code == 200
    assert len(response.json()["lines"]) == 100


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


# ------------------------------------------------------------- duplicating


def _meal_with(client, name, servings, *lines):
    meal = client.post(
        "/api/meals",
        json={
            "name": name,
            "servings": servings,
            "ingredients": [{"name": n, "qty": q, "unit": u} for n, q, u in lines],
        },
    ).json()
    return meal


def _amounts(meal):
    return sorted((i["name"], i["qty"], i["unit"]) for i in meal["ingredients"])


def test_duplicating_a_meal_copies_its_servings_and_ingredients(client):
    curry = _meal_with(
        client, "Chicken curry", 4, ("Chicken thigh", 500, "g"), ("Onion", 2, "")
    )

    response = client.post(f"/api/meals/{curry['id']}/duplicate")

    assert response.status_code == 201
    copy = response.json()
    assert response.headers["location"] == f"/api/meals/{copy['id']}"
    assert (copy["name"], copy["servings"]) == ("Chicken curry (copy)", 4)
    assert copy["id"] != curry["id"]
    assert _amounts(copy) == _amounts(curry)


def test_a_duplicate_is_its_own_meal(client):
    curry = _meal_with(client, "Curry", 2, ("Onion", 2, ""))
    copy = client.post(f"/api/meals/{curry['id']}/duplicate").json()
    onion = copy["ingredients"][0]["ingredient_id"]

    client.patch(
        f"/api/meals/{copy['id']}/ingredients/{onion}", json={"qty": 5, "unit": ""}
    )
    client.post(
        f"/api/meals/{copy['id']}/ingredients",
        json={"name": "Chickpeas", "qty": 1, "unit": "can"},
    )

    original = client.get(f"/api/meals/{curry['id']}").json()
    assert _amounts(original) == [("Onion", 2, "")]


def test_a_duplicate_is_not_planned(client):
    curry = _meal_with(client, "Curry", 2)
    client.put(
        f"/api/plan/{MONDAY.isoformat()}",
        json={"days": [{"day": "Monday", "meal_id": curry["id"], "servings": 2}]},
    )

    copy = client.post(f"/api/meals/{curry['id']}/duplicate").json()

    plan = client.get(f"/api/plan/{MONDAY.isoformat()}").json()
    planned = {d["meal_id"] for d in plan["days"]} - {None}
    assert planned == {curry["id"]} != {copy["id"]}


def test_each_copy_takes_the_next_free_name(client):
    curry = _meal_with(client, "Curry", 2)

    names = [
        client.post(f"/api/meals/{curry['id']}/duplicate").json()["name"]
        for _ in range(3)
    ]

    assert names == ["Curry (copy)", "Curry (copy 2)", "Curry (copy 3)"]


def test_a_copy_of_a_copy_counts_on_from_the_original(client):
    curry = _meal_with(client, "Curry", 2)
    first = client.post(f"/api/meals/{curry['id']}/duplicate").json()

    second = client.post(f"/api/meals/{first['id']}/duplicate").json()

    assert second["name"] == "Curry (copy 2)"


def test_a_freed_name_is_used_again(client):
    curry = _meal_with(client, "Curry", 2)
    first = client.post(f"/api/meals/{curry['id']}/duplicate").json()
    client.post(f"/api/meals/{curry['id']}/duplicate")
    client.delete(f"/api/meals/{first['id']}")

    again = client.post(f"/api/meals/{curry['id']}/duplicate").json()

    assert again["name"] == "Curry (copy)"


def test_a_copy_of_a_long_name_still_fits(client):
    name = "x" * 200
    meal = _meal_with(client, name, 1)

    copy = client.post(f"/api/meals/{meal['id']}/duplicate").json()

    assert copy["name"] == "x" * 193 + " (copy)"
    # The copy can be saved again as it is: it is within the limit.
    assert (
        client.patch(
            f"/api/meals/{copy['id']}", json={"name": copy["name"], "servings": 1}
        ).status_code
        == 200
    )


def test_duplicating_an_unknown_meal_is_a_404(client):
    response = client.post("/api/meals/999999/duplicate")

    assert response.status_code == 404
    assert client.get("/api/meals").json() == []


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


def test_grocery_list_says_the_aisle_and_buys_counted_things_whole(client):
    # The API loads the catalogue as it starts, so Lettuce is known.
    meal = _create_meal(client, "Caesar Salad", servings=4)
    client.post(
        f"/api/meals/{meal['id']}/ingredients",
        json={"name": "Lettuce", "qty": 1, "unit": ""},
    )
    client.put(
        f"/api/plan/{MONDAY.isoformat()}",
        json={"days": [{"day": "Monday", "meal_id": meal["id"], "servings": 2}]},
    )

    lines = client.get(f"/api/grocery-list/{MONDAY.isoformat()}").json()

    assert lines == [
        {
            "key": "lettuce|",
            "name": "Lettuce",
            "qty": 1,
            "unit": "",
            "display": "1",
            "category": "produce",
            "state": None,
            "extra_id": None,
        }
    ]


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
    suggestions = {s["name"]: s["unit"] for s in body["ingredient_suggestions"]}
    # Their own, with the unit they used, and the catalogue's.
    assert suggestions["Pasta"] == "g"
    assert suggestions["Beef Mince"] == "g"
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
        ("put", "/api/meals/999/ingredients", {"ingredients": []}),
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


def test_planning_a_meal_that_does_not_exist_is_a_404(client):
    response = client.put(
        f"/api/plan/{MONDAY}",
        json={"days": [{"day": "Monday", "meal_id": 999, "servings": 2}]},
    )

    assert response.status_code == 404
    assert client.get(f"/api/plan/{MONDAY}").json()["days"] == []


# --------------------------------------------------- suggesting meals


def _plan(client, week: date, **days: int) -> None:
    response = client.put(
        f"/api/plan/{week.isoformat()}",
        json={
            "days": [{"day": day, "meal_id": meal_id} for day, meal_id in days.items()]
        },
    )
    assert response.status_code == 200, response.text


def _suggest(client, week: date, empty: list[str], planned: list[int] = ()):
    params = [("empty", day) for day in empty] + [("planned", m) for m in planned]
    response = client.get(f"/api/plan/{week.isoformat()}/suggestions", params=params)
    assert response.status_code == 200, response.text
    return {d["day"]: d["meal_id"] for d in response.json()["days"]}


def test_empty_days_get_the_meals_not_cooked_recently(client):
    soup, tacos, curry = (
        _create_meal(client, n)["id"] for n in ("Soup", "Tacos", "Curry")
    )
    _plan(client, MONDAY - timedelta(weeks=1), Monday=tacos)
    _plan(client, MONDAY - timedelta(weeks=5), Monday=soup)

    # Curry never cooked, soup five weeks ago, tacos last week.
    assert _suggest(client, MONDAY, ["Monday", "Tuesday", "Wednesday"]) == {
        "Monday": curry,
        "Tuesday": soup,
        "Wednesday": tacos,
    }


def test_suggesting_saves_nothing_and_skips_meals_already_on_the_week(client):
    soup, tacos = (_create_meal(client, n)["id"] for n in ("Soup", "Tacos"))

    assert _suggest(client, MONDAY, ["Tuesday"], planned=[soup]) == {"Tuesday": tacos}
    assert client.get(f"/api/plan/{MONDAY.isoformat()}").json()["days"] == []


def test_suggestions_answer_for_the_week_containing_the_date(client):
    _create_meal(client, "Soup")

    response = client.get(
        f"/api/plan/{WEDNESDAY.isoformat()}/suggestions", params={"empty": "Friday"}
    )

    assert response.json()["week_start"] == MONDAY.isoformat()


def test_someone_elses_history_is_not_used(client):
    mine = _create_meal(client, "Soup")["id"]
    with api_client() as someone_else:
        theirs = _create_meal(someone_else, "Tacos")["id"]
        _plan(someone_else, MONDAY - timedelta(weeks=9), Monday=theirs)

        assert _suggest(someone_else, MONDAY, ["Monday", "Tuesday"]) == {
            "Monday": theirs
        }
    assert _suggest(client, MONDAY, ["Monday", "Tuesday"]) == {"Monday": mine}


def test_a_day_that_is_not_a_weekday_is_refused_for_suggestions(client):
    response = client.get(
        f"/api/plan/{MONDAY.isoformat()}/suggestions", params={"empty": "Funday"}
    )

    assert response.status_code == 422
