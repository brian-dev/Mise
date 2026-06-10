"""AI pricing fallback (AI_LAYER §9).

Estimates rough retail prices for items the deterministic USDA path couldn't
price (count units like "2 cloves", cross-dimension, or ingredients with no
baseline). Uses the cheap Haiku model with a forced tool. This is a fallback —
the calibrated USDA baseline stays the primary source (ARCHITECTURE §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from .anthropic_client import Usage, call_tool
from .config import settings
from .tools import EMIT_PRICES_TOOL, PRICING_SYSTEM_PROMPT


@dataclass
class PricingItem:
    name: str
    quantity: Decimal
    unit: str


@dataclass
class PricingResult:
    prices: list[Decimal]  # one per input item, same order
    usage: Usage


class PricingError(Exception):
    pass


def estimate_prices(
    items: list[PricingItem],
    region: str | None = None,
    store: str | None = None,
) -> PricingResult:
    """Estimate a rough total price for each item's quantity (AI_LAYER §9)."""
    if not items:
        return PricingResult(prices=[], usage=Usage(0, 0, 0, 0))

    payload = {
        "region": region,
        "store": store,
        "items": [
            {"name": it.name, "quantity": float(it.quantity), "unit": it.unit}
            for it in items
        ],
    }
    messages = [
        {
            "role": "user",
            "content": "Estimate prices for these items:\n\n"
            + json.dumps(payload, sort_keys=True, indent=2),
        }
    ]
    result = call_tool(
        model=settings.recipe_model,  # Haiku — cheap numeric lookup
        system_prompt=PRICING_SYSTEM_PROMPT,
        tool=EMIT_PRICES_TOOL,
        messages=messages,
    )
    rows = result.tool_input.get("prices", [])
    if len(rows) != len(items):
        raise PricingError(
            f"model returned {len(rows)} prices for {len(items)} items"
        )
    prices = [Decimal(str(r["estimated_price"])).quantize(Decimal("0.01")) for r in rows]
    return PricingResult(prices=prices, usage=result.usage)


@dataclass
class ResolveResult:
    prices: list[Decimal]  # one per item, all filled
    sources: list[str]  # "spoonacular" | "ai" per item
    usage: Usage


def resolve_prices(
    items: list[PricingItem],
    region: str | None = None,
    store: str | None = None,
) -> ResolveResult:
    """Price every item: paid-tier Spoonacular first (when configured), AI estimate
    for whatever it can't price; free tier is AI-only (ARCHITECTURE §7)."""
    if not items:
        return ResolveResult(prices=[], sources=[], usage=Usage(0, 0, 0, 0))

    if not settings.spoonacular_api_key:
        ai = estimate_prices(items, region, store)
        return ResolveResult(prices=ai.prices, sources=["ai"] * len(items), usage=ai.usage)

    from .spoonacular import spoonacular_prices

    sp = spoonacular_prices(items)
    misses = [i for i, p in enumerate(sp) if p is None]
    usage = Usage(0, 0, 0, 0)
    ai_by_index: dict[int, Decimal] = {}
    if misses:
        ai = estimate_prices([items[i] for i in misses], region, store)
        usage = ai.usage
        ai_by_index = {i: ai.prices[j] for j, i in enumerate(misses)}

    prices: list[Decimal] = []
    sources: list[str] = []
    for i in range(len(items)):
        spi = sp[i]
        if spi is not None:
            prices.append(spi)
            sources.append("spoonacular")
        else:
            prices.append(ai_by_index[i])
            sources.append("ai")
    return ResolveResult(prices=prices, sources=sources, usage=usage)
