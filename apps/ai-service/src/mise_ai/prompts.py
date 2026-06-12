"""Builds the dynamic per-request user message (AI_LAYER §3).

This is the only volatile part of the prompt — it sits after the cached
system + tool prefix, so it never invalidates the cache.
"""

from __future__ import annotations

import json
from typing import Any

from .schemas import MealPlanRequest, RecipeRequest


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
        "cuisines": req.cuisines,
        "cuisine_hint": req.cuisine_hint,
    }
    # Deterministic serialization (sorted keys) keeps the block stable for any
    # given request — relevant once we cache per-request context.
    return (
        "Generate a meal plan for this household and date range:\n\n"
        + json.dumps(context, sort_keys=True, indent=2)
    )


def build_recipe_context(req: RecipeRequest, base_recipe: dict[str, Any] | None = None) -> str:
    """Compact JSON context for a single-recipe swap/iteration (AI_LAYER §8)."""
    context: dict[str, Any] = {
        "meal_type": req.meal_type.value,
        "servings": req.servings,
        "dietary": {"flags": req.dietary.flags, "avoid": req.dietary.avoid_text},
        "pantry": [
            {"name": p.name, "quantity": p.quantity, "unit": p.unit.value}
            for p in req.pantry
        ],
        "avoid_titles": req.avoid_titles,
        "modify": req.modify,
    }
    if base_recipe is not None:
        context["base_recipe"] = base_recipe
    return (
        "Generate one recipe for this meal slot:\n\n"
        + json.dumps(context, sort_keys=True, indent=2)
    )
