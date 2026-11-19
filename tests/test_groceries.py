"""The grocery list as the shopper uses it (server/routers/groceries.py):
ticks kept per user and week, extras, usuals and the aisle order."""

from __future__ import annotations

import itertools

import pytest
from api_client import api_client

from app.models import Category
from app.repositories import MAX_EXTRAS_PER_WEEK

#: A week far from any sample plan a new guest is given.
WEEK = "2030-01-07"
NEXT_WEEK = "2030-01-14"
PROBLEM = "urn:meal-planner:problem:"


@pytest.fixture
def client(db):
    with api_client() as test_client:
        yield test_client


_meal_names = itertools.count(1)


def _plan_meal(client, *lines: tuple[str, float, str], week: str = WEEK) -> None:
    """A new meal with these ingredients, planned on the week's Monday."""
    meal = client.post(
        "/api/meals",
        json={
            "name": f"Meal {next(_meal_names)}",
            "servings": 2,
            "ingredients": [
                {"name": name, "qty": qty, "unit": unit} for name, qty, unit in lines
            ],
        },
    )
    assert meal.status_code == 201, meal.text
    planned = client.put(
        f"/api/plan/{week}",
        json={"days": [{"day": "Monday", "meal_id": meal.json()["id"]}]},
    )
    assert planned.status_code == 200, planned.text


def _groceries(client, week: str = WEEK) -> dict:
    response = client.get(f"/api/groceries/{week}")
    assert response.status_code == 200, response.text
    return response.json()


def _lines(client, week: str = WEEK) -> dict[str, dict]:
    return {line["name"]: line for line in _groceries(client, week)["lines"]}


def _tick(client, key: str, state: str | None, week: str = WEEK) -> None:
    response = client.put(
        f"/api/groceries/{week}/checks", json={"key": key, "state": state}
    )
    assert response.status_code == 204, response.text


def _add(client, text: str, week: str = WEEK):
    return client.post(f"/api/groceries/{week}/extras", json={"text": text})


# --- Ticks ---------------------------------------------------------------------


def test_a_tick_is_kept_and_shows_on_another_device(db) -> None:
    with api_client(as_guest=False) as laptop:
        signed_up = laptop.post(
            "/api/auth/signup",
            json={"email": "cook@example.com", "password": "lettuce harbour spoon"},
        )
        assert signed_up.status_code == 200, signed_up.text
        _plan_meal(laptop, ("Pasta", 400, "g"), ("Onion", 1, ""))
        _tick(laptop, _lines(laptop)["Pasta"]["key"], "basket")

    with api_client(as_guest=False) as phone:
        logged_in = phone.post(
            "/api/auth/login",
            json={"email": "cook@example.com", "password": "lettuce harbour spoon"},
        )
        assert logged_in.status_code == 200, logged_in.text
        lines = _lines(phone)

    assert lines["Pasta"]["state"] == "basket"
    assert lines["Onion"]["state"] is None


def test_a_tick_belongs_to_its_week(client) -> None:
    _plan_meal(client, ("Pasta", 400, "g"), week=WEEK)
    _plan_meal(client, ("Pasta", 400, "g"), week=NEXT_WEEK)

    _tick(client, _lines(client)["Pasta"]["key"], "basket")

    assert _lines(client, WEEK)["Pasta"]["state"] == "basket"
    assert _lines(client, NEXT_WEEK)["Pasta"]["state"] is None


def test_a_tick_holds_when_the_amount_changes(client) -> None:
    """Keyed by name and unit: planning more pasta keeps it ticked."""
    _plan_meal(client, ("Pasta", 400, "g"))
    _tick(client, _lines(client)["Pasta"]["key"], "basket")

    _plan_meal(client, ("Pasta", 100, "g"), week=WEEK)  # replaces Monday's meal

    assert _lines(client)["Pasta"]["state"] == "basket"


def test_marking_at_home_then_back_to_get(client) -> None:
    _plan_meal(client, ("Olive Oil", 2, "tbsp"))
    key = _lines(client)["Olive Oil"]["key"]

    _tick(client, key, "have")
    assert _lines(client)["Olive Oil"]["state"] == "have"

    _tick(client, key, None)
    assert _lines(client)["Olive Oil"]["state"] is None


def test_starting_again_empties_the_basket_but_remembers_what_is_at_home(
    client,
) -> None:
    _plan_meal(client, ("Pasta", 400, "g"), ("Olive Oil", 2, "tbsp"))
    lines = _lines(client)
    _tick(client, lines["Pasta"]["key"], "basket")
    _tick(client, lines["Olive Oil"]["key"], "have")

    response = client.delete(f"/api/groceries/{WEEK}/basket")

    assert response.status_code == 200, response.text
    states = {line["name"]: line["state"] for line in response.json()["lines"]}
    assert states == {"Pasta": None, "Olive Oil": "have"}


def test_ticks_are_never_seen_or_changed_by_someone_else(client) -> None:
    _plan_meal(client, ("Pasta", 400, "g"))
    key = _lines(client)["Pasta"]["key"]
    _tick(client, key, "basket")

    with api_client() as stranger:
        _plan_meal(stranger, ("Pasta", 400, "g"))
        assert _lines(stranger)["Pasta"]["state"] is None
        _tick(stranger, key, None)
        stranger.delete(f"/api/groceries/{WEEK}/basket")

    assert _lines(client)["Pasta"]["state"] == "basket"


def test_a_tick_must_say_a_known_state(client) -> None:
    response = client.put(
        f"/api/groceries/{WEEK}/checks", json={"key": "pasta|g", "state": "eaten"}
    )
    assert response.status_code == 422


# --- Extras --------------------------------------------------------------------


def test_an_extra_is_read_like_a_recipe_line_and_finds_its_aisle(client) -> None:
    response = _add(client, "2 L milk")

    assert response.status_code == 200, response.text
    (milk,) = response.json()["lines"]
    assert milk["name"] == "Milk"
    assert milk["display"] == "2 L"
    assert milk["category"] == "dairy"
    assert milk["extra_id"] is not None
    assert milk["key"] == "+milk"


def test_an_extra_with_no_amount_or_aisle(client) -> None:
    (line,) = _add(client, "bin bags").json()["lines"]

    assert (line["name"], line["qty"], line["display"]) == ("Bin bags", None, "")
    assert line["category"] is None


def test_an_extra_sits_beside_the_meals_lines_in_aisle_order(client) -> None:
    _plan_meal(client, ("Pasta", 400, "g"), ("Onion", 1, ""))

    lines = _add(client, "milk").json()["lines"]

    assert [line["name"] for line in lines] == ["Onion", "Milk", "Pasta"]


def test_adding_an_extra_again_changes_its_amount(client) -> None:
    _add(client, "1 L milk")

    lines = _add(client, "3 L Milk").json()["lines"]

    assert [(line["name"], line["display"]) for line in lines] == [("Milk", "3 L")]


def test_a_removed_extra_comes_back_unticked(client) -> None:
    (milk,) = _add(client, "milk").json()["lines"]
    _tick(client, milk["key"], "basket")

    removed = client.delete(f"/api/groceries/{WEEK}/extras/{milk['extra_id']}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["lines"] == []

    (again,) = _add(client, "milk").json()["lines"]
    assert again["state"] is None


def test_an_extra_belongs_to_its_week_and_its_person(client) -> None:
    (milk,) = _add(client, "milk").json()["lines"]

    assert _lines(client, NEXT_WEEK) == {}
    with api_client() as stranger:
        assert _lines(stranger) == {}
        gone = stranger.delete(f"/api/groceries/{WEEK}/extras/{milk['extra_id']}")
        assert gone.status_code == 404
        assert gone.json()["type"] == f"{PROBLEM}grocery-item-not-found"
    assert "Milk" in _lines(client)


def test_an_extra_must_name_something(client) -> None:
    response = _add(client, "2 kg")

    assert response.status_code == 422
    assert response.json()["type"] == f"{PROBLEM}nothing-to-add"
    assert response.json()["detail"] == "Say what to add, like 2 L milk."


def test_a_weeks_extras_are_capped_but_one_already_there_can_change(client) -> None:
    # Spelled-out names: "thing 5" would read as five of "Thing".
    names = [f"thing {chr(97 + n // 26)}{chr(97 + n % 26)}" for n in range(101)]
    for name in names[:MAX_EXTRAS_PER_WEEK]:
        assert _add(client, name).status_code == 200

    refused = _add(client, names[MAX_EXTRAS_PER_WEEK])
    changed = _add(client, f"2 {names[0]}")

    assert refused.status_code == 422
    assert refused.json()["type"] == f"{PROBLEM}grocery-limit"
    assert changed.status_code == 200


# --- Usuals --------------------------------------------------------------------


def test_usuals_are_added_to_a_week_in_one_go(client) -> None:
    client.post("/api/usuals", json={"text": "2 L milk"})
    usuals = client.post("/api/usuals", json={"text": "bread"}).json()
    assert [(u["name"], u["display"]) for u in usuals] == [
        ("Bread", ""),
        ("Milk", "2 L"),
    ]

    response = client.post(f"/api/groceries/{WEEK}/add-usuals")

    assert response.status_code == 200, response.text
    names = {line["name"]: line["display"] for line in response.json()["lines"]}
    assert names == {"Milk": "2 L", "Bread": ""}


def test_adding_usuals_keeps_an_amount_already_on_the_list(client) -> None:
    client.post("/api/usuals", json={"text": "2 L milk"})
    _add(client, "4 L milk")

    lines = client.post(f"/api/groceries/{WEEK}/add-usuals").json()["lines"]

    assert [(line["name"], line["display"]) for line in lines] == [("Milk", "4 L")]


def test_an_extra_kept_as_a_usual(client) -> None:
    (milk,) = _add(client, "2 L milk").json()["lines"]

    kept = client.post(f"/api/groceries/{WEEK}/extras/{milk['extra_id']}/keep")

    assert kept.status_code == 200, kept.text
    assert [(u["name"], u["display"]) for u in kept.json()["usuals"]] == [
        ("Milk", "2 L")
    ]
    # And next week, one click away.
    lines = client.post(f"/api/groceries/{NEXT_WEEK}/add-usuals").json()["lines"]
    assert [line["name"] for line in lines] == ["Milk"]


def test_a_usual_removed(client) -> None:
    (usual,) = client.post("/api/usuals", json={"text": "bread"}).json()

    assert client.delete(f"/api/usuals/{usual['id']}").json() == []
    again = client.delete(f"/api/usuals/{usual['id']}")
    assert again.status_code == 404


def test_usuals_are_private(client) -> None:
    (usual,) = client.post("/api/usuals", json={"text": "bread"}).json()

    with api_client() as stranger:
        assert _groceries(stranger)["usuals"] == []
        assert stranger.delete(f"/api/usuals/{usual['id']}").status_code == 404

    assert len(_groceries(client)["usuals"]) == 1


# --- Aisle order ---------------------------------------------------------------


def test_the_default_aisle_order_is_the_catalogues(client) -> None:
    assert _groceries(client)["aisle_order"] == [c.value for c in Category]


def test_a_chosen_aisle_order_sorts_every_week(client) -> None:
    _plan_meal(client, ("Pasta", 400, "g"), ("Onion", 1, ""), ("Milk", 1, "L"))
    order = ["pantry", "dairy", "produce", "meat", "bakery", "frozen"]

    saved = client.put("/api/aisle-order", json={"aisle_order": order})

    assert saved.status_code == 200, saved.text
    assert saved.json() == order
    groceries = _groceries(client)
    assert groceries["aisle_order"] == order
    assert [line["name"] for line in groceries["lines"]] == ["Pasta", "Milk", "Onion"]


@pytest.mark.parametrize(
    "order",
    [
        ["produce", "meat", "dairy", "bakery", "pantry"],  # one missing
        ["produce", "produce", "dairy", "bakery", "pantry", "frozen"],  # repeated
        ["produce", "meat", "dairy", "bakery", "pantry", "frozen", "garden"],
    ],
)
def test_an_aisle_order_must_list_every_aisle_once(client, order) -> None:
    assert (
        client.put("/api/aisle-order", json={"aisle_order": order}).status_code == 422
    )


def test_an_aisle_order_is_private(client) -> None:
    order = ["frozen", "pantry", "bakery", "dairy", "meat", "produce"]
    client.put("/api/aisle-order", json={"aisle_order": order})

    with api_client() as stranger:
        assert _groceries(stranger)["aisle_order"] == [c.value for c in Category]


# --- Leaving -------------------------------------------------------------------


def test_deleting_an_account_takes_its_grocery_state_with_it(client, db) -> None:
    _plan_meal(client, ("Pasta", 400, "g"))
    _tick(client, _lines(client)["Pasta"]["key"], "basket")
    _add(client, "milk")
    client.post("/api/usuals", json={"text": "bread"})
    client.put(
        "/api/aisle-order",
        json={"aisle_order": list(reversed([c.value for c in Category]))},
    )

    assert client.delete("/api/account").status_code in (200, 204)

    with db.engine.connect() as connection:
        for table in (
            "grocery_checks",
            "grocery_extras",
            "grocery_usuals",
            "grocery_settings",
        ):
            count = connection.exec_driver_sql(f"SELECT count(*) FROM {table}")
            assert count.scalar_one() == 0, table
