"""Tests for unit conversion and quantity formatting."""

from __future__ import annotations

import pytest

from app.units import format_qty, normalize


@pytest.mark.parametrize(
    ("qty", "unit", "expected"),
    [
        (1, "kg", (1000.0, "g")),
        (500, "mg", (0.5, "g")),
        (200, "g", (200.0, "g")),
        (2, "L", (2000.0, "ml")),
        (250, "ml", (250.0, "ml")),
    ],
)
def test_metric_units_convert_to_their_base(qty, unit, expected):
    assert normalize(qty, unit) == expected


@pytest.mark.parametrize("unit", ["tbsp", "tsp", "cup", "cloves", "slices"])
def test_ambiguous_or_unknown_units_are_left_unconverted(unit):
    """Region-dependent units keep their value; merging is not worth a wrong number."""
    assert normalize(3, unit) == (3, unit)


@pytest.mark.parametrize(
    ("unit", "expected"), [("KG", "g"), (" Tbsp ", "tbsp"), (None, ""), ("", "")]
)
def test_units_are_cased_and_trimmed_consistently(unit, expected):
    assert normalize(1, unit)[1] == expected


@pytest.mark.parametrize(
    ("qty", "expected"),
    [(400.0, "400"), (2.0, "2"), (0.5, "0.5"), (2.25, "2.25"), (0, "0")],
)
def test_whole_numbers_render_without_a_decimal_tail(qty, expected):
    assert format_qty(qty) == expected
