"""Finding the recipe in a recipe website's page.

Recipe sites describe their recipes for search engines in schema.org
`Recipe` data, as JSON-LD in a `<script type="application/ld+json">` tag:
the name, how many it serves (`recipeYield`) and the ingredient lines
(`recipeIngredient`). Reading that rather than the page's visible markup
means one reader works for every site that does it, and nothing breaks
when a site redesigns.

The Recipe may be the whole block, one of a list, inside an `@graph`, or
nested deeper (a page's `mainEntity`). Its `@type` may be a list, or
written as a full IRI. Every field is checked for shape, because the data
is whatever the page says.

Pure: the page comes in as text, so this is tested against saved pages.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any

#: The most lines kept, and the longest, as the parse endpoint allows.
MAX_LINES = 100
MAX_LINE_LENGTH = 200
MAX_NAME_LENGTH = 200
#: How deep into the data to look for the Recipe; real pages need 3 or 4.
_MAX_DEPTH = 8

_TAG = re.compile(r"<[^>]*>")
#: A script tag's type attribute; read from at most `_MAX_TAG` characters.
_TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'>]+)""")
_MAX_TAG = 500
_NUMBER = re.compile(r"\d{1,4}")  # bounded: int() of a huge one is slow


@dataclass(frozen=True, slots=True)
class FoundRecipe:
    #: "" when the page gives no name.
    name: str
    #: None when the page does not say, or says something unreadable.
    servings: int | None
    lines: list[str]


def find_recipe(page: str) -> FoundRecipe | None:
    """The first Recipe with ingredients in the page's JSON-LD, if any."""
    for block in _json_ld_blocks(page):
        try:
            data = json.loads(block, strict=False)
        except (ValueError, RecursionError):
            continue
        recipe = _find(data, 0)
        if recipe is not None:
            return recipe
    return None


def _json_ld_blocks(page: str) -> list[str]:
    """The text of every `<script type="application/ld+json">`.

    A scan with `str.find`, each search starting where the last stopped, so
    it is linear in the page. Not `html.parser`, which is quadratic on some
    inputs (two megabytes of "<" took minutes), nor a regex like
    `<script.*?</script>`, which rescans to the end for every unclosed tag:
    the page is whatever its author wanted it to be.
    """
    lower = page.lower()
    blocks: list[str] = []
    position = 0
    while (start := lower.find("<script", position)) != -1:
        tag_end = lower.find(">", start)
        if tag_end == -1:
            break
        close = lower.find("</script", tag_end)
        if close == -1:
            break
        if _is_json_ld(lower[start : min(tag_end, start + _MAX_TAG)]):
            blocks.append(page[tag_end + 1 : close])
        position = close + len("</script")
    return blocks


def _is_json_ld(tag: str) -> bool:
    kind = _TYPE.search(tag)
    return bool(kind) and kind.group(1).split(";")[0].strip() == "application/ld+json"


def _find(data: Any, depth: int) -> FoundRecipe | None:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(data, list):
        for item in data:
            found = _find(item, depth + 1)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    if _is_recipe(data.get("@type")):
        lines = _lines(data.get("recipeIngredient", data.get("ingredients")))
        if lines:
            return FoundRecipe(_name(data.get("name")), _servings(data), lines)
    for value in data.values():
        if isinstance(value, (dict, list)):
            found = _find(value, depth + 1)
            if found:
                return found
    return None


def _is_recipe(kind: Any) -> bool:
    kinds = kind if isinstance(kind, list) else [kind]
    return any(
        isinstance(k, str) and k.rsplit("/", 1)[-1].rsplit(":", 1)[-1] == "Recipe"
        for k in kinds
    )


def _text(value: str, limit: int) -> str:
    """Plain text: entities decoded, any markup dropped, spacing tidied, at
    most `limit` characters. Cut first, generously, so no pattern ever runs
    over a string of the page's choosing length."""
    value = html.unescape(value[: limit * 8])
    return " ".join(_TAG.sub(" ", value).split())[:limit]


def _lines(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    lines = [_text(item, MAX_LINE_LENGTH) for item in items if isinstance(item, str)]
    return [line for line in lines if line][:MAX_LINES]


def _name(value: Any) -> str:
    return _text(value, MAX_NAME_LENGTH) if isinstance(value, str) else ""


def _servings(recipe: dict[str, Any]) -> int | None:
    """The first number in `recipeYield` (or `yield`): "4", 4, "Serves 4-6",
    ["4", "4 servings"]. Anything outside 1 to 100 is not believed."""
    value = recipe.get("recipeYield", recipe.get("yield"))
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str) and (match := _NUMBER.search(value)):
        number = int(match.group())
    else:
        return None
    return number if 1 <= number <= 100 else None
