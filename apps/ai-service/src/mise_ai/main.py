"""FastAPI application entrypoint.

Scaffold only. The generation endpoints (ARCHITECTURE.md §5, docs/AI_LAYER.md)
are stubbed and will be implemented in the first AI-service feature PR:

    POST /v1/meal-plans/generate   -> job kind "meal_plan"   (async)
    POST /v1/recipes/generate      -> job kind "recipe"       (async)
    POST /v1/recipes/{id}/iterate  -> job kind "recipe_iterate"(async)
    POST /v1/pricing/estimate      -> synchronous
"""

from decimal import Decimal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .db import connect, persist_meal_plan
from .generation import GenerationError, generate_meal_plan
from .schemas import GeneratedMealPlan, MealPlanRequest
from .shopping import build_shopping_list

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


class ShoppingListRequest(BaseModel):
    meal_plan_id: UUID


class ShoppingListResponse(BaseModel):
    shopping_list_id: UUID
    estimated_total: Decimal
    budget: Decimal | None
    over_budget: bool
    items_total: int
    items_priced: int
    items_unpriced: int


@app.post("/v1/shopping-lists/build", response_model=ShoppingListResponse)
def build_list(req: ShoppingListRequest) -> ShoppingListResponse:
    """Build a draft shopping list from a meal plan (ARCHITECTURE §7, spec §3.5).

    Aggregates required quantities, subtracts the pantry, prices against the USDA
    baseline, and reconciles against the plan budget.
    """
    try:
        with connect() as conn:
            result = build_shopping_list(conn, req.meal_plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ShoppingListResponse(
        shopping_list_id=result.shopping_list_id,
        estimated_total=result.estimated_total,
        budget=result.budget,
        over_budget=result.over_budget,
        items_total=result.items_total,
        items_priced=result.items_priced,
        items_unpriced=result.items_unpriced,
    )
