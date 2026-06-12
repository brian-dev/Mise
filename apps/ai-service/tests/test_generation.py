"""Offline tests for the generation pipeline (no network).

Exercises schema validation, semantic checks, default-filling, and the repair
loop with a stubbed Anthropic call.
"""

from __future__ import annotations

import pytest

import mise_ai.generation as gen
from mise_ai.anthropic_client import ToolCallResult, Usage
from mise_ai.config import settings
from mise_ai.generation import GenerationError, MealPlanResult, generate_meal_plan
from mise_ai.schemas import GeneratedMealPlan, MealPlanRequest


@pytest.fixture(autouse=True)
def _one_shot(monkeypatch) -> None:
    # These exercise the one-shot path's validation/repair; pin parallel off so a
    # multi-day request doesn't fan out into per-day calls.
    monkeypatch.setattr(settings, "parallel_generation", False)


def _req(**over: object) -> MealPlanRequest:
    base = {
        "household_id": "00000000-0000-0000-0000-000000000001",
        "start_date": "2026-06-10",
        "end_date": "2026-06-11",
        "household_size": 4,
        "meal_types": ["dinner"],
    }
    base.update(over)
    return MealPlanRequest.model_validate(base)


def _recipe(title: str = "Sheet-Pan Chicken") -> dict:
    return {
        "title": title,
        "cuisine_tags": ["american"],
        "default_servings": 4,
        "instructions": "Roast everything at 425F for 30 minutes.",
        "ingredients": [
            {"name": "chicken thigh", "quantity": 2, "unit": "lb"},
            {"name": "yellow onion", "quantity": 1, "unit": "unit"},
        ],
    }


def _plan(dates: list[str]) -> dict:
    return {
        "days": [
            {"date": d, "meals": [{"meal_type": "dinner", "recipe": _recipe()}]}
            for d in dates
        ]
    }


def _usage() -> Usage:
    return Usage(
        input_tokens=10,
        output_tokens=20,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


def _stub_call(monkeypatch, plans: list[dict]) -> None:
    """Make call_tool return successive payloads from `plans`."""
    calls = iter(plans)

    def fake_call_tool(**_kwargs: object) -> ToolCallResult:
        return ToolCallResult(tool_input=next(calls), usage=_usage(), raw_content=[])

    monkeypatch.setattr(gen, "call_tool", fake_call_tool)


def test_valid_plan_passes(monkeypatch) -> None:
    _stub_call(monkeypatch, [_plan(["2026-06-10", "2026-06-11"])])
    result = generate_meal_plan(_req())
    assert result.repair_attempts == 0
    assert len(result.plan.days) == 2
    # servings defaulted to household_size
    assert result.plan.days[0].meals[0].servings == 4


def test_missing_date_triggers_repair_then_succeeds(monkeypatch) -> None:
    _stub_call(
        monkeypatch,
        [_plan(["2026-06-10"]), _plan(["2026-06-10", "2026-06-11"])],
    )
    result = generate_meal_plan(_req())
    assert result.repair_attempts == 1
    assert len(result.usage) == 2  # initial + one repair


def test_unrepairable_plan_raises(monkeypatch) -> None:
    # Always missing the second day -> fails after the one allowed repair.
    _stub_call(monkeypatch, [_plan(["2026-06-10"]), _plan(["2026-06-10"])])
    try:
        generate_meal_plan(_req())
    except GenerationError as e:
        assert "Missing dates" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected GenerationError")


def test_missing_meal_type_is_semantic_error(monkeypatch) -> None:
    plan = _plan(["2026-06-10", "2026-06-11"])
    # Request breakfast too, but the plan only has dinner.
    _stub_call(monkeypatch, [plan, plan])
    try:
        generate_meal_plan(_req(meal_types=["dinner", "breakfast"]))
    except GenerationError as e:
        assert "missing meal types" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected GenerationError")


def test_parallel_merges_days_in_order(monkeypatch) -> None:
    """With parallel on, each day is generated independently and merged in order."""
    monkeypatch.setattr(settings, "parallel_generation", True)

    def fake_one_shot(req: MealPlanRequest) -> MealPlanResult:
        # Return a one-day plan for whatever single day was requested.
        plan = GeneratedMealPlan.model_validate(_plan([req.start_date.isoformat()]))
        return MealPlanResult(plan=plan, usage=[_usage()], repair_attempts=0)

    monkeypatch.setattr(gen, "_generate_one_shot", fake_one_shot)
    result = generate_meal_plan(_req())  # 2-day request -> 2 concurrent calls
    assert [d.date.isoformat() for d in result.plan.days] == ["2026-06-10", "2026-06-11"]
    assert len(result.usage) == 2  # one usage entry per day


def test_day_hints_no_preference_rotates_defaults() -> None:
    hints = gen._day_hints([], 3)
    assert hints == gen._CUISINES[:3]


def test_day_hints_prefers_chosen_with_wildcard_every_fifth() -> None:
    chosen = ["Italian", "Mexican"]
    hints = gen._day_hints(chosen, 6)
    # Days 0-3 + 5 rotate the chosen list; day 4 (every 5th) is an off-list wildcard.
    assert hints[0] == "Italian"
    assert hints[1] == "Mexican"
    assert hints[2] == "Italian"
    assert hints[3] == "Mexican"
    assert hints[4] not in {"Italian", "Mexican"}  # wildcard for variety
    assert hints[5] == "Italian"


def test_day_hints_passes_cuisine_through_parallel(monkeypatch) -> None:
    """The per-day requests in parallel generation carry the chosen-cuisine hints."""
    monkeypatch.setattr(settings, "parallel_generation", True)
    seen: dict[str, str | None] = {}

    def fake_one_shot(req: MealPlanRequest) -> MealPlanResult:
        seen[req.start_date.isoformat()] = req.cuisine_hint
        plan = GeneratedMealPlan.model_validate(_plan([req.start_date.isoformat()]))
        return MealPlanResult(plan=plan, usage=[_usage()], repair_attempts=0)

    monkeypatch.setattr(gen, "_generate_one_shot", fake_one_shot)
    generate_meal_plan(_req(cuisines=["Thai"]))  # 2-day request
    assert seen["2026-06-10"] == "Thai"
    assert seen["2026-06-11"] == "Thai"
