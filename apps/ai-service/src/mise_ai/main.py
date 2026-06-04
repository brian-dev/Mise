"""FastAPI application entrypoint.

Scaffold only. The generation endpoints (ARCHITECTURE.md §5, docs/AI_LAYER.md)
are stubbed and will be implemented in the first AI-service feature PR:

    POST /v1/meal-plans/generate   -> job kind "meal_plan"   (async)
    POST /v1/recipes/generate      -> job kind "recipe"       (async)
    POST /v1/recipes/{id}/iterate  -> job kind "recipe_iterate"(async)
    POST /v1/pricing/estimate      -> synchronous
"""

from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .db import connect, persist_meal_plan
from .generation import GenerationError, generate_meal_plan
from .schemas import GeneratedMealPlan, MealPlanRequest

app = FastAPI(title="Mise AI Service", version="0.0.0")


@app.get("/v1/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe (ARCHITECTURE.md §5)."""
    return {"status": "ok"}


class MealPlanUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


class MealPlanResponse(BaseModel):
    meal_plan_id: UUID
    plan: GeneratedMealPlan
    repair_attempts: int
    usage: list[MealPlanUsage]


@app.post("/v1/meal-plans/generate", response_model=MealPlanResponse)
def generate(req: MealPlanRequest) -> MealPlanResponse:
    """Generate a full meal plan and persist it as a draft (AI_LAYER §2, §5, §7).

    Synchronous for now; the async job + Realtime wiring (ARCHITECTURE §5) is a
    follow-up.
    """
    try:
        result = generate_meal_plan(req)
    except GenerationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    with connect() as conn:
        meal_plan_id = persist_meal_plan(conn, result.plan, req)

    return MealPlanResponse(
        meal_plan_id=meal_plan_id,
        plan=result.plan,
        repair_attempts=result.repair_attempts,
        usage=[MealPlanUsage(**vars(u)) for u in result.usage],
    )
