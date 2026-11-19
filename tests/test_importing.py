"""Importing a recipe from a link, through the API.

The page fetch is replaced (tests never touch the network; app/fetch.py's
own rules are tested in test_fetch.py), so these test what the route does
with a page: read it, refuse it, and count it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api_client import api_client

from app import importing
from app.fetch import FetchRefused, Page
from app.ratelimit import IMPORTS_PER_USER

URL = "https://fixture.example/ragu/"
PAGES = Path(__file__).parent / "fixtures" / "recipes"


def fixture_page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


@pytest.fixture
def client(db):
    with api_client() as test_client:
        yield test_client


@pytest.fixture
def pages(monkeypatch):
    """What each URL "serves": a page's text, or a FetchRefused to raise.
    Records the URLs asked for, and the unchecked origin passed with them."""
    served: dict[str, str | FetchRefused] = {URL: fixture_page("wordpress-graph.html")}
    asked: list[tuple[str, str | None]] = []

    def fake_fetch(url: str, *, unchecked_origin: str | None = None) -> Page:
        asked.append((url, unchecked_origin))
        answer = served[url]
        if isinstance(answer, FetchRefused):
            raise answer
        return Page(url, answer)

    monkeypatch.setattr(importing, "fetch_page", fake_fetch)
    return served, asked


def _import(client, url: str = URL):
    return client.post("/api/recipes/import", json={"url": url})


def test_a_recipe_page_is_read_for_a_preview(client, pages):
    response = _import(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["servings"], body["url"]) == (
        "Weeknight Beef Ragu",
        6,
        URL,
    )
    lines = {line["text"]: line for line in body["lines"]}
    assert len(lines) == 8
    tomatoes = lines["2 x 400 g cans diced tomatoes"]
    assert (tomatoes["qty"], tomatoes["unit"], tomatoes["name"]) == (
        800,
        "g",
        "Diced Tomatoes",
    )
    parmesan = lines["½ cup grated parmesan, to serve"]
    assert (parmesan["qty"], parmesan["unit"]) == (0.5, "cups")


def test_importing_saves_nothing(client, pages):
    _import(client)

    assert client.get("/api/meals").json() == []


def test_a_page_with_no_recipe_says_so(client, pages):
    served, _ = pages
    served[URL] = fixture_page("no-recipe.html")

    response = _import(client)

    assert response.status_code == 422
    assert response.json()["type"].endswith("recipe-import")
    assert response.json()["detail"].startswith("No recipe found on that page.")


def test_a_refused_fetch_is_explained(client, pages):
    served, _ = pages
    served[URL] = FetchRefused("That address can't be fetched from here.")

    response = _import(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "That address can't be fetched from here."


def test_imports_are_limited_per_user_and_failures_count(client, pages):
    served, _ = pages
    served["https://fixture.example/missing/"] = FetchRefused("Gone.")
    for n in range(IMPORTS_PER_USER.limit):
        # Every other one fails: a failure must use up the allowance too,
        # or failing imports would be a free way to make the server fetch.
        url = URL if n % 2 else "https://fixture.example/missing/"
        assert _import(client, url).status_code in (200, 422)

    response = _import(client)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert "paste the ingredients instead" in response.json()["detail"]


def test_the_limit_is_each_users_own(client, pages):
    for _ in range(IMPORTS_PER_USER.limit):
        _import(client)
    assert _import(client).status_code == 429

    with api_client() as someone_else:
        assert _import(someone_else).status_code == 200


def test_the_link_is_bounded(client, pages):
    response = _import(client, "https://fixture.example/" + "a" * 2_000)

    assert response.status_code == 422
    assert response.json()["type"].endswith("request-validation")


def test_importing_needs_a_session(db, pages):
    with api_client(as_guest=False) as anonymous:
        assert _import(anonymous).status_code == 401


# --- The end-to-end tests' exemption --------------------------------------------


def test_the_fixture_origin_is_passed_on_outside_vercel(client, pages, monkeypatch):
    monkeypatch.setenv(importing.UNCHECKED_ORIGIN_ENV_VAR, "http://127.0.0.1:4175")
    monkeypatch.delenv("VERCEL", raising=False)
    _, asked = pages

    _import(client)

    assert asked == [(URL, "http://127.0.0.1:4175")]


def test_the_fixture_origin_is_ignored_on_vercel(monkeypatch):
    """Set there by mistake, it still opens no hole in production."""
    monkeypatch.setenv(importing.UNCHECKED_ORIGIN_ENV_VAR, "http://127.0.0.1:4175")
    monkeypatch.setenv("VERCEL", "1")

    assert importing.unchecked_origin() is None


# --- Creating the meal it previews -----------------------------------------------


def test_a_meal_is_created_with_its_ingredients_in_one_request(client):
    response = client.post(
        "/api/meals",
        json={
            "name": "Weeknight Beef Ragu",
            "servings": 6,
            "ingredients": [
                {"name": "Beef Mince", "qty": 500, "unit": "g"},
                {"name": "Garlic", "qty": 2, "unit": "clove"},
            ],
        },
    )

    assert response.status_code == 201, response.text
    meal = client.get(response.headers["location"]).json()
    assert meal["servings"] == 6
    assert sorted((i["name"], i["qty"], i["unit"]) for i in meal["ingredients"]) == [
        ("Beef Mince", 500, "g"),
        ("Garlic", 2, "cloves"),
    ]


def test_a_meal_whose_ingredients_cannot_be_saved_is_not_created(client):
    response = client.post(
        "/api/meals",
        json={
            "name": "Half a meal",
            "ingredients": [
                {"name": "Butter", "qty": 50, "unit": "g"},
                {"name": "Butter", "qty": 1, "unit": "tbsp"},
            ],
        },
    )

    assert response.status_code == 409
    assert client.get("/api/meals").json() == []


def test_renaming_a_meal_does_not_take_ingredients(client):
    meal = client.post("/api/meals", json={"name": "Soup"}).json()

    response = client.patch(
        f"/api/meals/{meal['id']}", json={"name": "Soup", "ingredients": []}
    )

    assert response.status_code == 422
