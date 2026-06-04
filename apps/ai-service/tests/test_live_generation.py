"""Live end-to-end smoke test against the real Claude API.

Skipped unless a real API key is configured. The key can come from the shell
env OR apps/ai-service/.env (both feed the service config), so either works:

    uv run pytest -m live -q                       # key in .env
    ANTHROPIC_API_KEY=sk-ant-... uv run pytest -m live -q
"""

from __future__ import annotations

import pytest

from mise_ai.config import settings
from mise_ai.generation import generate_meal_plan
from mise_ai.schemas import MealPlanRequest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not settings.anthropic_api_key,
        reason="no ANTHROPIC_API_KEY configured (shell env or .env)",
    ),
]


def test_live_two_day_dinner_plan() -> None:
    req = MealPlanRequest.model_validate(
        {
            "household_id": "00000000-0000-0000-0000-000000000001",
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
