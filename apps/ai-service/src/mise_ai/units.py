"""Unit conversion for pricing (spec §3.6).

Converts a recipe quantity into the ingredient's USDA pricing unit so it can be
priced against the baseline. Only same-dimension conversions are possible:
mass↔mass and volume↔volume. Cross-dimension (mass↔volume, which needs a
density) and count units (clove/can/unit/…) return None — those fall back to the
AI price estimate or stay unpriced. The goal is a rough estimate (~±10%), so
standard factors are fine.
"""

from __future__ import annotations

from decimal import Decimal

# Mass → grams.
_MASS: dict[str, Decimal] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}

# Volume → millilitres.
_VOLUME: dict[str, Decimal] = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "tsp": Decimal("4.92892159375"),
    "tbsp": Decimal("14.78676478125"),
    "cup": Decimal("236.5882365"),
    "fl_oz": Decimal("29.5735295625"),
}


def convert_quantity(qty: Decimal, from_unit: str, to_unit: str) -> Decimal | None:
    """Convert `qty` from one unit to another, or None if not convertible."""
    if from_unit == to_unit:
        return qty
    for table in (_MASS, _VOLUME):
        if from_unit in table and to_unit in table:
            return qty * table[from_unit] / table[to_unit]
    return None
