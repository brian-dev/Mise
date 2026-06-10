"""Offline unit-conversion tests (spec §3.6)."""

from __future__ import annotations

from decimal import Decimal

from mise_ai.units import convert_quantity


def test_same_unit_is_identity() -> None:
    assert convert_quantity(Decimal("3"), "lb", "lb") == Decimal("3")


def test_mass_conversions() -> None:
    # 16 oz == 1 lb
    assert convert_quantity(Decimal("16"), "oz", "lb") == Decimal("1")
    # 453.59237 g == 1 lb
    got = convert_quantity(Decimal("453.59237"), "g", "lb")
    assert got is not None and abs(got - Decimal("1")) < Decimal("1e-9")
    # 1 kg == 1000 g
    assert convert_quantity(Decimal("1"), "kg", "g") == Decimal("1000")


def test_volume_conversions() -> None:
    assert convert_quantity(Decimal("1"), "l", "ml") == Decimal("1000")
    # 1 cup == 236.5882365 ml
    got = convert_quantity(Decimal("1"), "cup", "ml")
    assert got is not None and abs(got - Decimal("236.5882365")) < Decimal("1e-6")


def test_incompatible_returns_none() -> None:
    assert convert_quantity(Decimal("1"), "lb", "ml") is None  # mass↔volume
    assert convert_quantity(Decimal("2"), "clove", "lb") is None  # count↔mass
    assert convert_quantity(Decimal("1"), "unit", "g") is None
