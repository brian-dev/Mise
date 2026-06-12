"""Meal-plan generation orchestration (AI_LAYER §2, §6).

Pipeline: build context -> forced tool call -> schema + semantic validation ->
one bounded repair retry -> return the validated plan with token usage.

Canonicalization and persistence (AI_LAYER §5, §7) are the next slice; this
module produces a validated GeneratedMealPlan and the usage needed for the
token-cost benchmark (AI_LAYER §11).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from .anthropic_client import Usage, call_tool
from .config import settings
from .prompts import build_context_block, build_recipe_context
from .schemas import GeneratedMealPlan, GeneratedRecipe, MealPlanRequest, RecipeRequest
from .tools import EMIT_RECIPE_TOOL, MEAL_PLAN_TOOL, RECIPE_SYSTEM_PROMPT, SYSTEM_PROMPT


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


# Cuisine rotation to keep concurrently-generated days distinct (they can't see
# each other's output). Broad enough to work across dietary constraints.
_CUISINES = ["Italian", "Mexican", "Indian", "Thai", "Mediterranean", "Japanese", "American"]


def _day_hints(cuisines: list[str], n_days: int) -> list[str]:
    """Per-day cuisine hints for parallel generation (each concurrent day can't see
    the others, so a hint keeps them distinct).

    With preferred `cuisines`, rotate through them but slot an off-list wildcard
    every 5th day for variety (~4 of 5 on-list). Without a preference, rotate the
    default set. Deterministic for a given input.
    """
    if not cuisines:
        return [_CUISINES[i % len(_CUISINES)] for i in range(n_days)]

    chosen_lower = {c.lower() for c in cuisines}
    wild = [c for c in _CUISINES if c.lower() not in chosen_lower] or _CUISINES
    hints: list[str] = []
    pi = wi = 0
    for i in range(n_days):
        if i % 5 == 4:  # every 5th day -> a wildcard off the preferred list
            hints.append(wild[wi % len(wild)])
            wi += 1
        else:
            hints.append(cuisines[pi % len(cuisines)])
            pi += 1
    return hints


def _single_day_request(
    req: MealPlanRequest, day: date, cuisine_hint: str | None = None
) -> MealPlanRequest:
    """A copy of the request scoped to one day (for parallel generation)."""
    update: dict[str, Any] = {"start_date": day, "end_date": day}
    if cuisine_hint is not None:
        update["cuisine_hint"] = cuisine_hint
    return req.model_copy(update=update)


def generate_meal_plan(req: MealPlanRequest) -> MealPlanResult:
    if req.end_date < req.start_date:
        raise GenerationError("end_date is before start_date.")

    days = [
        req.start_date + timedelta(days=i)
        for i in range((req.end_date - req.start_date).days + 1)
    ]
    if len(days) > 1 and settings.parallel_generation:
        return _generate_parallel(req, days)
    return _generate_one_shot(req)


def _generate_parallel(req: MealPlanRequest, days: list[date]) -> MealPlanResult:
    """Fan out one single-day generation per day, concurrently, then merge.

    Each per-day call reuses the validated one-shot path. Trade-off: days are
    generated independently, so cross-day variety is weaker than a one-shot plan
    (AI_LAYER §D1) — acceptable for the latency win.
    """
    workers = min(len(days), settings.parallel_max_workers)
    hints = _day_hints(req.cuisines, len(days))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _generate_one_shot,
                _single_day_request(req, d, req.cuisine_hint or hints[i]),
            ): d
            for i, d in enumerate(days)
        }
        by_day: dict[date, MealPlanResult] = {}
        for fut in as_completed(futures):
            by_day[futures[fut]] = fut.result()  # GenerationError propagates -> job fails

    merged_days = []
    usages: list[Usage] = []
    repairs = 0
    for d in days:  # stable, chronological order
        res = by_day[d]
        merged_days.extend(res.plan.days)
        usages.extend(res.usage)
        repairs += res.repair_attempts
    return MealPlanResult(
        plan=GeneratedMealPlan(days=merged_days), usage=usages, repair_attempts=repairs
    )


def _generate_one_shot(req: MealPlanRequest) -> MealPlanResult:
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


@dataclass
class RecipeResult:
    recipe: GeneratedRecipe
    usage: list[Usage]
    repair_attempts: int


def generate_recipe(
    req: RecipeRequest, base_recipe: dict[str, Any] | None = None
) -> RecipeResult:
    """Generate one recipe for a meal swap/iteration (AI_LAYER §8).

    Uses the cheaper recipe model (Haiku). Same bounded-repair discipline as the
    full plan, but the only semantic check is schema validity.
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_recipe_context(req, base_recipe)}
    ]
    usages: list[Usage] = []

    for attempt in range(settings.max_repair_attempts + 1):
        result = call_tool(
            model=settings.recipe_model,
            system_prompt=RECIPE_SYSTEM_PROMPT,
            tool=EMIT_RECIPE_TOOL,
            messages=messages,
        )
        usages.append(result.usage)
        try:
            recipe = GeneratedRecipe.model_validate(result.tool_input)
        except ValidationError as e:
            if attempt >= settings.max_repair_attempts:
                raise GenerationError(f"Recipe failed validation: {e}") from e
            tool_use_id = None
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
                            "content": f"The recipe was invalid. Fix and re-emit:\n{e}",
                        }
                    ],
                }
            )
            continue
        return RecipeResult(recipe=recipe, usage=usages, repair_attempts=attempt)

    raise GenerationError("Unreachable: recipe repair loop exited without returning.")
