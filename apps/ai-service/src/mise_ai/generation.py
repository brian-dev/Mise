"""Meal-plan generation orchestration (AI_LAYER §2, §6).

Pipeline: build context -> forced tool call -> schema + semantic validation ->
one bounded repair retry -> return the validated plan with token usage.

Canonicalization and persistence (AI_LAYER §5, §7) are the next slice; this
module produces a validated GeneratedMealPlan and the usage needed for the
token-cost benchmark (AI_LAYER §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from .anthropic_client import Usage, call_tool
from .config import settings
from .prompts import build_context_block
from .schemas import GeneratedMealPlan, MealPlanRequest
from .tools import MEAL_PLAN_TOOL, SYSTEM_PROMPT


class GenerationError(Exception):
    """Raised when generation fails validation after the allowed repair attempts."""


@dataclass
class MealPlanResult:
    plan: GeneratedMealPlan
    usage: list[Usage]  # one entry per model call (initial + any repairs)
    repair_attempts: int

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usage)


def _semantic_errors(plan: GeneratedMealPlan, req: MealPlanRequest) -> list[str]:
    """Checks the JSON Schema can't express (AI_LAYER §6)."""
    errors: list[str] = []

    expected_dates = set()
    d = req.start_date
    while d <= req.end_date:
        expected_dates.add(d)
        d += timedelta(days=1)

    got_dates = [day.date for day in plan.days]
    if len(got_dates) != len(set(got_dates)):
        errors.append("Duplicate dates in the plan.")
    missing = expected_dates - set(got_dates)
    extra = set(got_dates) - expected_dates
    if missing:
        errors.append(f"Missing dates: {sorted(d.isoformat() for d in missing)}.")
    if extra:
        errors.append(f"Unexpected dates not in the requested range: "
                      f"{sorted(d.isoformat() for d in extra)}.")

    requested_meals = {m.value for m in req.meal_types}
    for day in plan.days:
        present = {m.meal_type.value for m in day.meals}
        absent = requested_meals - present
        if absent:
            errors.append(f"{day.date.isoformat()} is missing meal types: {sorted(absent)}.")

    return errors


def _apply_defaults(plan: GeneratedMealPlan, req: MealPlanRequest) -> None:
    """Fill omitted per-meal servings with the household size (AI_LAYER §6)."""
    for day in plan.days:
        for meal in day.meals:
            if meal.servings is None:
                meal.servings = req.household_size


def _validate(
    tool_input: dict[str, Any], req: MealPlanRequest
) -> tuple[GeneratedMealPlan | None, list[str]]:
    try:
        plan = GeneratedMealPlan.model_validate(tool_input)
    except ValidationError as e:
        return None, [str(e)]
    semantic = _semantic_errors(plan, req)
    if semantic:
        return None, semantic
    return plan, []


def generate_meal_plan(req: MealPlanRequest) -> MealPlanResult:
    if req.end_date < req.start_date:
        raise GenerationError("end_date is before start_date.")

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_context_block(req)}
    ]
    usages: list[Usage] = []

    for attempt in range(settings.max_repair_attempts + 1):
        result = call_tool(
            model=settings.meal_plan_model,
            system_prompt=SYSTEM_PROMPT,
            tool=MEAL_PLAN_TOOL,
            messages=messages,
        )
        usages.append(result.usage)

        plan, errors = _validate(result.tool_input, req)
        if plan is not None:
            _apply_defaults(plan, req)
            return MealPlanResult(plan=plan, usage=usages, repair_attempts=attempt)

        if attempt >= settings.max_repair_attempts:
            raise GenerationError(
                "Meal plan failed validation after "
                f"{attempt + 1} attempt(s): {errors}"
            )

        # Repair turn: echo the model's tool_use, return the errors as a tool
        # result, and ask for a corrected plan (AI_LAYER §6).
        tool_use_id: str | None = None
        for b in result.raw_content:
            if b.type == "tool_use":
                tool_use_id = b.id
                break
        messages.append({"role": "assistant", "content": result.raw_content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "is_error": True,
                        "content": (
                            "The plan was invalid. Fix these issues and emit the "
                            "corrected plan via emit_meal_plan:\n- "
                            + "\n- ".join(errors)
                        ),
                    }
                ],
            }
        )

    raise GenerationError("Unreachable: repair loop exited without returning.")
