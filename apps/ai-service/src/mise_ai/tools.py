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
        "$defs": {
            "recipe": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "cuisine_tags",
                    "default_servings",
                    "instructions",
                    "ingredients",
                ],
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
            },
        },
    },
}
