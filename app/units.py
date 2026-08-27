"""Normalizing measurement units so equivalent amounts can be summed."""

from __future__ import annotations

#: Conversions to a canonical base unit per family. Deliberately limited to
#: metric mass and volume, whose ratios are exact and universal.
#:
#: tsp/tbsp/cup are intentionally absent: their real size varies by region
#: (an Australian metric cup is 250 ml, a US cup is ~237 ml), so converting
#: them would silently produce a wrong number. Leaving them unconverted
#: merely fails to merge, which is visible and harmless.
_CONVERSIONS_TO_BASE: dict[str, tuple[str, float]] = {
    "mg": ("g", 0.001),
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
}


def normalize(qty: float, unit: str | None) -> tuple[float, str]:
    """Convert an amount to its family's base unit.

    Units outside the convertible families are returned unchanged apart
    from being lower-cased and stripped, so "Tbsp" and "tbsp" still merge
    with each other even though neither is converted.

    Returns the (quantity, unit) pair to accumulate under.
    """
    unit_key = (unit or "").strip().lower()
    if unit_key in _CONVERSIONS_TO_BASE:
        base_unit, factor = _CONVERSIONS_TO_BASE[unit_key]
        return qty * factor, base_unit
    return qty, unit_key


def format_qty(qty: float) -> str:
    """Render a quantity without a trailing ".0" on whole numbers.

    Grocery lists read better as "400 g" and "2 cloves" than as
    "400.0 g" and "2.0 cloves".
    """
    rounded = round(qty, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"
