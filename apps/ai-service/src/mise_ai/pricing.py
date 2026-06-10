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
