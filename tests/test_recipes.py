"""Finding the recipe in a page (app/recipes.py), against saved pages.

The pages in tests/fixtures/recipes/ are written for these tests in the
shapes recipe sites use: a WordPress SEO plugin's @graph, a bare Recipe, a
list with a multi-valued @type, a Recipe as a page's mainEntity, and a page
with no JSON-LD recipe at all.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.recipes import MAX_LINE_LENGTH, MAX_LINES, FoundRecipe, find_recipe

PAGES = Path(__file__).parent / "fixtures" / "recipes"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def with_recipe(recipe: object) -> str:
    return f'<script type="application/ld+json">{json.dumps(recipe)}</script>'


def test_a_recipe_in_a_wordpress_graph() -> None:
    recipe = find_recipe(page("wordpress-graph.html"))

    assert recipe == FoundRecipe(
        name="Weeknight Beef Ragu",
        servings=6,
        lines=[
            "500 g beef mince",
            "1 brown onion, finely chopped",
            "2 garlic cloves, crushed",
            "2 x 400 g cans diced tomatoes",
            "2 tbsp tomato paste",
            "1 cup (250ml) beef stock",
            "½ cup grated parmesan, to serve",  # &frac12; decoded
            "500 g pappardelle",
        ],
    )


def test_a_plain_recipe_with_markup_and_entities_in_it() -> None:
    recipe = find_recipe(page("plain-recipe.html"))

    assert recipe is not None
    assert recipe.name == "Chicken & Leek Pie"
    assert recipe.servings == 4
    # Tags dropped, the blank line skipped.
    assert recipe.lines == [
        "600g chicken thighs",
        "2 leeks, sliced",
        "1 sheet puff pastry",
        "300 ml cream",
    ]


def test_the_recipe_among_other_blocks_some_broken() -> None:
    recipe = find_recipe(page("several-blocks.html"))

    assert recipe == FoundRecipe("Lentil Soup", 4, ["1 cup red lentils"])


def test_a_recipe_nested_in_a_page_with_older_field_names() -> None:
    recipe = find_recipe(page("nested-main-entity.html"))

    assert recipe == FoundRecipe(
        "Pancakes", 12, ["2 cups self-raising flour", "2 eggs", "1 1/2 cups milk"]
    )


def test_a_page_with_no_recipe_data() -> None:
    """Microdata and plain scripts are not read: only JSON-LD."""
    assert find_recipe(page("no-recipe.html")) is None


@pytest.mark.parametrize(
    ("value", "servings"),
    [
        (4, 4),
        ("4", 4),
        ("4 servings", 4),
        ("Serves 4-6", 4),
        (["8", "8 pieces"], 8),
        ([], None),
        ("a crowd", None),
        (0, None),
        ("500", None),
        (True, None),
        ({"value": 4}, None),
        ("9" * 5_000, None),  # bounded: no slow conversion of a huge number
    ],
)
def test_servings_are_read_from_the_yield(value, servings) -> None:
    recipe = find_recipe(
        with_recipe(
            {"@type": "Recipe", "recipeYield": value, "recipeIngredient": ["x"]}
        )
    )

    assert recipe is not None
    assert recipe.servings == servings


def test_a_recipe_without_ingredients_is_passed_over() -> None:
    page_text = with_recipe(
        [
            {"@type": "Recipe", "name": "Video only", "recipeIngredient": []},
            {
                "@type": "Recipe",
                "name": "Toast",
                "recipeIngredient": ["2 slices bread"],
            },
        ]
    )

    recipe = find_recipe(page_text)

    assert recipe is not None
    assert recipe.name == "Toast"


def test_fields_of_the_wrong_shape_are_ignored() -> None:
    recipe = find_recipe(
        with_recipe(
            {
                "@type": "Recipe",
                "name": {"text": "not a string"},
                "recipeIngredient": ["2 eggs", 7, None, {"x": 1}],
            }
        )
    )

    assert recipe == FoundRecipe("", None, ["2 eggs"])


def test_lines_are_bounded_as_the_parser_is() -> None:
    recipe = find_recipe(
        with_recipe({"@type": "Recipe", "recipeIngredient": ["1 egg " * 100] * 500})
    )

    assert recipe is not None
    assert len(recipe.lines) == MAX_LINES
    assert all(len(line) <= MAX_LINE_LENGTH for line in recipe.lines)


_SCRIPT = '<script type="application/ld+json">'
_PAGE = 2_000_000  # the most app/fetch.py will read


@pytest.mark.parametrize(
    "hostile",
    [
        "<" * _PAGE,
        "<a " * (_PAGE // 3),
        "<script>" * (_PAGE // 8),
        _SCRIPT + "x" * _PAGE,
        (_SCRIPT + "</script>") * (_PAGE // 45),
        '<a b="' + "x" * _PAGE,
        _SCRIPT + "[" * (_PAGE // 2) + "</script>",
        _SCRIPT + '{"a":' * (_PAGE // 5) + "</script>",
        with_recipe({"@type": "Recipe", "recipeIngredient": ["<" * _PAGE]}),
        with_recipe([{"a": 1}] * (_PAGE // 8)),
    ],
    ids=[
        "angle brackets",
        "open tags",
        "unclosed scripts",
        "unclosed json",
        "many scripts",
        "unclosed attribute",
        "deep list",
        "deep object",
        "one huge line",
        "wide data",
    ],
)
def test_a_hostile_page_the_largest_fetched_is_read_quickly(hostile) -> None:
    """Linear, not quadratic: html.parser took minutes on two megabytes of
    "<", which a page could be built to contain."""
    start = time.perf_counter()
    find_recipe(hostile)

    # Linear reading takes well under a second here; the quadratic reading
    # this guards against took minutes. Generous, because CI's Postgres job
    # runs Python several times slower: 1 s failed there at 1.1 s.
    assert time.perf_counter() - start < 10.0


def test_the_type_attribute_is_read_loosely() -> None:
    recipe = {"@type": "Recipe", "recipeIngredient": ["2 eggs"]}
    page_text = (
        f'<SCRIPT TYPE="Application/LD+JSON; charset=utf-8">{json.dumps(recipe)}'
        "</SCRIPT>"
    )

    assert find_recipe(page_text) is not None
