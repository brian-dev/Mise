"""Live end-to-end smoke test against the real Claude API.

Skipped unless a real ANTHROPIC_API_KEY is set (the value must be non-empty).
Run locally with your key to validate forced tool use, prompt caching, and
usage capture:

    ANTHROPIC_API_KEY=sk-ant-... uv run pytest -m live -q
"""

from __future__ import annotations

import os

import pytest

from mise_ai.generation import generate_meal_plan
from mise_ai.schemas import MealPlanRequest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="no real ANTHROPIC_API_KEY in env",
    ),
]


def test_live_two_day_dinner_plan() -> None:
    req = MealPlanRequest.model_validate(
        {
            "start_date": "2026-06-10",
            "end_date": "2026-06-11",
            "household_size": 2,
            "meal_types": ["dinner"],
            "dietary": {"flags": ["vegetarian"], "avoid_text": "no mushrooms"},
            "pantry": [{"name": "yellow onion", "quantity": 3, "unit": "unit"}],
            "budget": 40,
            "region": "Texas",
        }
    )
    result = generate_meal_plan(req)

    dates = {d.date.isoformat() for d in result.plan.days}
    assert dates == {"2026-06-10", "2026-06-11"}
    for day in result.plan.days:
        assert {m.meal_type.value for m in day.meals} == {"dinner"}
        for meal in day.meals:
            assert meal.recipe.ingredients  # non-empty
    assert result.usage and result.usage[0].output_tokens > 0
