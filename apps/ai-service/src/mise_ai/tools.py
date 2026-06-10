"""The `emit_meal_plan` tool schema and the stable system prompt.

These are the cacheable, volatile-free parts of the prompt (AI_LAYER §3). They
must stay byte-identical across requests so the prompt-cache prefix hits — do
not interpolate dates, IDs, or per-request data here.
"""

from __future__ import annotations

from typing import Any

# Controlled unit vocabulary (AI_LAYER §D4) — mirror of schemas.Unit.
_UNITS = [
    "g", "kg", "oz", "lb",
    "ml", "l", "tsp", "tbsp", "cup", "fl_oz",
    "unit", "clove", "slice", "can", "bunch", "pinch",
]

SYSTEM_PROMPT = """\
You are Mise's meal-planning engine. You generate complete, practical meal \
plans that a home cook can actually shop for and make.

Hard rules:
- Emit the plan ONLY by calling the `emit_meal_plan` tool. No prose.
- Cover every requested date exactly once, and within each day cover exactly \
the requested meal types.
- Treat dietary `flags` as HARD constraints (never violate). Treat `avoid_text` \
as a strong soft preference.
- Prefer ingredients already in the provided pantry before introducing new ones \
("use what you have first").
- Honor the variety target across the week.
- Quantities must use ONLY this unit vocabulary: \
""" + ", ".join(_UNITS) + """.
- Use plain, canonical ingredient names (e.g. "yellow onion", not \
"1 medium onion, diced"). Quantity and unit carry the amount; the name is the \
ingredient.
- Scale recipe `default_servings` to the household size unless a recipe is \
naturally portioned differently.
- Keep recipes realistic: sensible prep/cook times and complete instructions.\
"""

# Recipe object schema — mirrors schemas.GeneratedRecipe (AI_LAYER §4). Shared by
# the meal-plan tool ($defs.recipe) and the single-recipe swap/iterate tool.
_RECIPE_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "cuisine_tags", "default_servings", "instructions", "ingredients"],
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "cuisine_tags": {"type": "array", "items": {"type": "string"}},
        "prep_time": {"type": "integer", "minimum": 0},
        "cook_time": {"type": "integer", "minimum": 0},
        "default_servings": {"type": "integer", "minimum": 1},
        "instructions": {"type": "string"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "quantity", "unit"],
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "quantity": {"type": "number", "exclusiveMinimum": 0},
                    "unit": {"type": "string", "enum": _UNITS},
                    "is_optional": {"type": "boolean"},
                },
            },
        },
    },
}

# JSON Schema for the tool. Mirrors schemas.GeneratedMealPlan (AI_LAYER §4).
MEAL_PLAN_TOOL: dict[str, Any] = {
    "name": "emit_meal_plan",
    "description": "Emit a complete meal plan for the requested date range.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["days"],
        "properties": {
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["date", "meals"],
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "meals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["meal_type", "recipe"],
                                "properties": {
                                    "meal_type": {
                                        "type": "string",
                                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                                    },
                                    "servings": {"type": "integer", "minimum": 1},
                                    "recipe": {"$ref": "#/$defs/recipe"},
                                },
                            },
                        },
                    },
                },
            },
        },
        "$defs": {"recipe": _RECIPE_OBJECT_SCHEMA},
    },
}


# Single-recipe tool for meal swaps / iteration (AI_LAYER §8). Same recipe shape.
EMIT_RECIPE_TOOL: dict[str, Any] = {
    "name": "emit_recipe",
    "description": "Emit a single recipe for one meal slot.",
    "input_schema": _RECIPE_OBJECT_SCHEMA,
}

RECIPE_SYSTEM_PROMPT = """\
You are Mise's recipe engine. You generate a single, practical recipe for one \
meal slot that a home cook can shop for and make.

Hard rules:
- Emit the recipe ONLY by calling the `emit_recipe` tool. No prose.
- Treat dietary `flags` as HARD constraints (never violate). Treat `avoid_text` \
as a strong soft preference.
- Prefer ingredients already in the provided pantry before introducing new ones.
- Make it DIFFERENT from the listed `avoid_titles` (the other meals this week).
- If `modify` is given, honor it (e.g. "spicier", "make it vegan", "use what I \
have") relative to the provided base recipe.
- Quantities must use ONLY this unit vocabulary: """ + ", ".join(_UNITS) + """.
- Use plain, canonical ingredient names; quantity + unit carry the amount.
- Scale `default_servings` to the requested servings.\
"""


# Pricing-estimate tool (AI_LAYER §9). Returns one price per input item, in order.
EMIT_PRICES_TOOL: dict[str, Any] = {
    "name": "emit_prices",
    "description": "Estimate a rough retail price for each shopping item, in order.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["prices"],
        "properties": {
            "prices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["estimated_price"],
                    "properties": {
                        "name": {"type": "string"},
                        "estimated_price": {"type": "number", "minimum": 0},
                    },
                },
            }
        },
    },
}

PRICING_SYSTEM_PROMPT = """\
You estimate typical U.S. grocery retail prices for a shopping list.

For each item you are given a name, a quantity, and a unit. Return the rough \
cost of buying THAT quantity at a typical grocery store, reasoning in terms of \
real retail packaging and prices (e.g. garlic sells ~3 heads for $1, a 14.5 oz \
can of tomatoes ~$1.20, onions ~$1/lb). Use the region/store hints if given.

Rules:
- Emit prices ONLY via the `emit_prices` tool, one entry PER input item, in the \
SAME ORDER. No prose.
- estimated_price is the total USD for the listed quantity (not per-unit).
- Aim to be within ~10% of typical actual cost — a rough estimate is fine. \
Never return 0 for a real item; estimate something reasonable.\
"""
