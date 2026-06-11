"""Open Food Facts / Open Prices lookup + pantry add-by-barcode.

Offline tests stub HTTP; the db test hits live Postgres (rolled back); one `live`
test hits the real OFF API (free, no key)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg
import pytest

import mise_ai.openfoodfacts as off
from mise_ai.db import add_to_pantry, get_pantry
from mise_ai.openfoodfacts import lookup_product


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def _fake_get(product_payload: Any, prices_payload: Any):
    def get(url: str, **_kw: Any) -> _Resp:
        if "prices" in url:
            return _Resp(200, prices_payload)
        return _Resp(200, product_payload)

    return get


def test_lookup_product_parses(monkeypatch) -> None:
    product = {
        "status": 1,
        "product": {"product_name": "Nutella", "brands": "Nutella, Yum", "quantity": "750 g"},
    }
    prices = {"items": [{"price": 4.50, "currency": "USD"}, {"price": 5.50, "currency": "USD"},
                        {"price": 3.0, "currency": "EUR"}]}
    monkeypatch.setattr(off.httpx, "get", _fake_get(product, prices))
    p = lookup_product("3017620422003")
    assert p is not None
    assert p.name == "Nutella"
    assert p.brand == "Nutella"  # first brand only
    assert p.quantity == "750 g"
    assert p.price == Decimal("5.00")  # median of the USD prices (EUR ignored)


def test_lookup_product_not_found(monkeypatch) -> None:
    monkeypatch.setattr(off.httpx, "get", _fake_get({"status": 0}, {"items": []}))
    assert lookup_product("0000") is None


def test_lookup_price_no_usd_is_none(monkeypatch) -> None:
    monkeypatch.setattr(
        off.httpx, "get", _fake_get({"status": 1, "product": {"product_name": "X"}},
                                    {"items": [{"price": 3.0, "currency": "EUR"}]})
    )
    p = lookup_product("123")
    assert p is not None and p.price is None  # only EUR available


@pytest.mark.db
def test_add_to_pantry_canonicalizes_and_upserts(conn: psycopg.Connection) -> None:
    from mise_ai.db import create_household

    household_id = create_household(conn, "BC HH")["id"]
    # "yellow onions" should canonicalize to the seeded "Yellow Onion".
    r1 = add_to_pantry(conn, household_id, "yellow onions", Decimal("2"), "lb")
    r2 = add_to_pantry(conn, household_id, "yellow onion", Decimal("3"), "lb")
    assert r1["ingredient_id"] == r2["ingredient_id"]  # same canonical ingredient
    pantry = get_pantry(conn, household_id)
    onion = next(p for p in pantry if p["name"] == "Yellow Onion")
    assert onion["quantity"] == Decimal("5.000")  # 2 + 3 upserted


@pytest.mark.live
def test_live_lookup_nutella() -> None:
    p = lookup_product("3017620422003")  # Nutella
    assert p is not None and "nutella" in p.name.lower()
