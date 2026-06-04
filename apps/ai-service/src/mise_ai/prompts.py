"""Builds the dynamic per-request user message (AI_LAYER §3).

This is the only volatile part of the prompt — it sits after the cached
system + tool prefix, so it never invalidates the cache.
"""

from __future__ import annotations

import json

from .schemas import MealPlanRequest


def build_context_block(req: MealPlanRequest) -> str:
    """Compact JSON context block describing what to generate."""
    context = {
        "date_range": {
            "start": req.start_date.isoformat(),
            "end": req.end_date.isoformat(),
        },
        "household_size": req.household_size,
        "meal_types": [m.value for m in req.meal_types],
        "dietary": {
            "flags": req.dietary.flags,
            "avoid": req.dietary.avoid_text,
        },
        "pantry": [
            {"name": p.name, "quantity": p.quantity, "unit": p.unit.value}
            for p in req.pantry
        ],
        "budget": req.budget,
        "region": req.region,
        "store_preference": req.store_preference,
        "variety_target": req.variety_target,
    }
    # Deterministic serialization (sorted keys) keeps the block stable for any
    # given request — relevant once we cache per-request context.
    return (
        "Generate a meal plan for this household and date range:\n\n"
        + json.dumps(context, sort_keys=True, indent=2)
    )
