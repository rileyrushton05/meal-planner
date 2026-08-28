"""Guards the frontend's hand-written types against the API's real schemas.

The TypeScript interfaces in web/src/api/types.ts are written by hand rather
than generated. That is fine for readability but silently rots: renaming a
Pydantic field would compile cleanly on both sides and only fail as
`undefined` in the browser. This compares the two directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from api import schemas

TYPES_FILE = Path(__file__).resolve().parents[1] / "web/src/api/types.ts"

#: TypeScript interface -> the Pydantic model it mirrors.
MIRRORED = {
    "IngredientAmount": schemas.IngredientAmount,
    "Meal": schemas.MealRead,
    "DayAssignment": schemas.DayAssignment,
    "GroceryLine": schemas.GroceryLine,
    "TemplateIngredient": schemas.TemplateIngredientRead,
    "MealTemplate": schemas.TemplateRead,
    "AppState": schemas.AppState,
    "WeekPlan": schemas.WeekPlanRead,
}


def parse_interfaces(source: str) -> dict[str, set[str]]:
    """Field names per `export interface` block.

    Deliberately simple: the file is small and deliberately plain, so a
    regex is clearer here than pulling in a TypeScript parser.
    """
    interfaces: dict[str, set[str]] = {}
    for match in re.finditer(
        r"export interface (\w+)\s*\{(.*?)\n\}", source, re.DOTALL
    ):
        name, body = match.group(1), match.group(2)
        fields = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith(("//", "/*", "*")):
                continue
            field = re.match(r"(\w+)\??\s*:", line)
            if field:
                fields.add(field.group(1))
        interfaces[name] = fields
    return interfaces


@pytest.fixture(scope="module")
def interfaces() -> dict[str, set[str]]:
    return parse_interfaces(TYPES_FILE.read_text())


def test_every_mirrored_interface_exists(interfaces):
    missing = set(MIRRORED) - set(interfaces)
    assert not missing, f"interfaces missing from types.ts: {sorted(missing)}"


@pytest.mark.parametrize(("interface_name", "model"), sorted(MIRRORED.items()))
def test_interface_matches_its_schema(
    interface_name: str, model: type[BaseModel], interfaces
):
    """The frontend must declare exactly the fields the API sends."""
    expected = set(model.model_fields)
    actual = interfaces[interface_name]

    assert actual == expected, (
        f"{interface_name} in types.ts does not match {model.__name__}.\n"
        f"  only in TypeScript: {sorted(actual - expected)}\n"
        f"  only in Python    : {sorted(expected - actual)}"
    )


def test_day_names_match_the_backend_enum(interfaces):
    """The DAYS tuple drives every day dropdown; it must match the enum."""
    from app.models import DayOfWeek

    source = TYPES_FILE.read_text()
    listed = re.search(r"export const DAYS = \[(.*?)\] as const", source, re.DOTALL)
    assert listed, "DAYS constant not found in types.ts"

    days = re.findall(r'"(\w+)"', listed.group(1))
    assert days == [day.value for day in DayOfWeek]
