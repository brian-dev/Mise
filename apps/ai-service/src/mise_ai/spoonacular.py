"""Spoonacular real-retail pricing provider (paid tier — ARCHITECTURE §7).

Uses the `parseIngredients` endpoint, which costs the whole batch in one call and
returns a per-ingredient `estimatedCost` (in US cents). Items Spoonacular can't
recognize come back as None and fall through to the AI estimate. Any HTTP/quota
failure returns all-None so pricing degrades gracefully to the free path.

Quota-friendly for the free dev subscription: one batched call per request plus a
short in-memory cache (ephemeral, no permanent storage of Spoonacular data).
"""

from __future__ import annotations

import time
from decimal import Decimal

import httpx

from .config import settings
from .pricing import PricingItem

_URL = "https://api.spoonacular.com/recipes/parseIngredients"
_TTL = 3600.0  # 1 hour, in-memory only
_CACHE: dict[tuple[str, str, str], tuple[Decimal, float]] = {}

# Render our unit vocabulary into natural phrasing Spoonacular parses well.
_UNIT_PHRASE = {"unit": "", "fl_oz": "fl oz"}


def _key(it: PricingItem) -> tuple[str, str, str]:
    return (it.name.strip().lower(), it.unit, str(it.quantity))


def _line(it: PricingItem) -> str:
    unit = _UNIT_PHRASE.get(it.unit, it.unit)
    parts = [f"{it.quantity:f}"]
    if unit:
        parts.append(unit)
    parts.append(it.name)
    return " ".join(parts)


def spoonacular_prices(items: list[PricingItem]) -> list[Decimal | None]:
    """A retail price (USD) per item, or None where unavailable."""
    if not items or not settings.spoonacular_api_key:
        return [None] * len(items)

    now = time.monotonic()
    prices: list[Decimal | None] = [None] * len(items)
    todo: list[int] = []
    for i, it in enumerate(items):
        cached = _CACHE.get(_key(it))
        if cached is not None and cached[1] > now:
            prices[i] = cached[0]
        else:
            todo.append(i)

    if todo:
        lines = "\n".join(_line(items[i]) for i in todo)
        try:
            resp = httpx.post(
                _URL,
                params={"apiKey": settings.spoonacular_api_key, "includeNutrition": "false"},
                data={"ingredientList": lines, "servings": 1},
                timeout=30,
            )
            results = resp.json() if resp.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            results = []  # network/quota/parse error -> AI fallback handles all

        for pos, i in enumerate(todo):
            row = results[pos] if pos < len(results) else {}
            cost = row.get("estimatedCost") if row.get("name") else None
            if cost and cost.get("value") is not None:
                price = (Decimal(str(cost["value"])) / Decimal("100")).quantize(Decimal("0.01"))
                prices[i] = price
                _CACHE[_key(items[i])] = (price, now + _TTL)

    return prices
