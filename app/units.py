"""Normalising measurement units so equivalent amounts can be summed."""

from __future__ import annotations

#: Metric mass and volume only. tsp/tbsp/cup vary by region (an Australian
#: cup is 250 ml, a US cup ~237 ml), so converting them would produce a
#: silently wrong number; leaving them alone merely fails to merge.
_CONVERSIONS_TO_BASE: dict[str, tuple[str, float]] = {
    "mg": ("g", 0.001),
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
}


def normalize(qty: float, unit: str | None) -> tuple[float, str]:
    """Convert an amount to its family's base unit.

    Unconvertible units are returned lower-cased and stripped, so "Tbsp" and
    "tbsp" still merge with each other.
    """
    unit_key = (unit or "").strip().lower()
    if unit_key in _CONVERSIONS_TO_BASE:
        base_unit, factor = _CONVERSIONS_TO_BASE[unit_key]
        return qty * factor, base_unit
    return qty, unit_key


#: Base unit -> the larger unit to switch to, and the threshold for doing so.
#: A shopping list reads better as "1.5 kg" than "1500 g".
_SCALE_UP = {
    "g": ("kg", 1000.0),
    "ml": ("L", 1000.0),
}


def humanize(qty: float, unit: str) -> tuple[float, str]:
    """Express an amount in the largest unit that keeps it above 1.

    Totals stay summed in the base unit, so this only affects presentation.
    """
    larger = _SCALE_UP.get(unit)
    if larger and qty >= larger[1]:
        name, factor = larger
        return qty / factor, name
    return qty, unit


def format_qty(qty: float) -> str:
    """Render a quantity without a trailing ".0" - "400 g", not "400.0 g"."""
    rounded = round(qty, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"
