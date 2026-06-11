"""Open Food Facts (product lookup) + Open Prices (crowd-sourced pricing).

OFF resolves a scanned barcode to a product name for the pantry add-by-barcode
flow (spec §3.4) — free and open, no key. Open Prices supplies a packaging-aware
crowd-sourced price keyed by barcode (paid-tier pricing data, ARCHITECTURE §7);
coverage is uneven and mostly non-US, so we only surface USD prices and return
None otherwise. Any HTTP error degrades to None.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal

import httpx

_OFF = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
_PRICES = "https://prices.openfoodfacts.org/api/v1/prices"
_UA = {"User-Agent": "Mise/0.0 (https://github.com/brian-dev/Mise)"}


@dataclass
class Product:
    barcode: str
    name: str
    brand: str | None
    quantity: str | None  # freeform packaging text, e.g. "750 g"
    price: Decimal | None  # USD, from Open Prices, if available


def lookup_product(barcode: str) -> Product | None:
    """Resolve a barcode to a product (name + packaging), or None if not found."""
    try:
        resp = httpx.get(
            _OFF.format(code=barcode),
            params={"fields": "code,product_name,brands,quantity"},
            headers=_UA,
            timeout=20,
        )
        data = resp.json() if resp.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("status") != 1:
        return None
    p = data.get("product", {})
    name = (p.get("product_name") or "").strip()
    if not name:
        return None
    brands = (p.get("brands") or "").split(",")[0].strip() or None
    quantity = (p.get("quantity") or "").strip() or None
    return Product(
        barcode=barcode, name=name, brand=brands, quantity=quantity,
        price=lookup_price(barcode),
    )


def lookup_price(barcode: str, currency: str = "USD") -> Decimal | None:
    """Median recent crowd-sourced price for the barcode in `currency`, or None."""
    try:
        resp = httpx.get(
            _PRICES,
            params={"product_code": barcode, "order_by": "-created", "size": 25},
            headers=_UA,
            timeout=20,
        )
        items = resp.json().get("items", []) if resp.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return None

    values = [
        float(it["price"])
        for it in items
        if it.get("currency") == currency and it.get("price") is not None
    ]
    if not values:
        return None
    return Decimal(str(statistics.median(values))).quantize(Decimal("0.01"))
