"""FastAPI application entrypoint.

Scaffold only. The generation endpoints (ARCHITECTURE.md §5, docs/AI_LAYER.md)
are stubbed and will be implemented in the first AI-service feature PR:

    POST /v1/meal-plans/generate   -> job kind "meal_plan"   (async)
    POST /v1/recipes/generate      -> job kind "recipe"       (async)
    POST /v1/recipes/{id}/iterate  -> job kind "recipe_iterate"(async)
    POST /v1/pricing/estimate      -> synchronous
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .db import (
    connect,
    create_household,
    get_meal_plan,
    get_pantry,
    get_shopping_list,
    list_households,
    persist_meal_plan,
)
from .generation import GenerationError, generate_meal_plan
from .pantry import cook_meal
from .schemas import GeneratedMealPlan, MealPlanRequest
from .shopping import build_shopping_list

app = FastAPI(title="Mise AI Service", version="0.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe (ARCHITECTURE.md §5)."""
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Read/helper endpoints for the local web harness (dev convenience).
# --------------------------------------------------------------------------- #
class HouseholdCreate(BaseModel):
    name: str


@app.get("/v1/households")
def households() -> list[dict[str, Any]]:
    with connect() as conn:
        return list_households(conn)


@app.post("/v1/households")
def new_household(req: HouseholdCreate) -> dict[str, Any]:
    with connect() as conn:
        return create_household(conn, req.name)


@app.get("/v1/households/{household_id}/pantry")
def pantry(household_id: UUID) -> list[dict[str, Any]]:
    with connect() as conn:
        return get_pantry(conn, household_id)


@app.get("/v1/meal-plans/{meal_plan_id}")
def meal_plan(meal_plan_id: UUID) -> dict[str, Any]:
    try:
        with connect() as conn:
            return get_meal_plan(conn, meal_plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/v1/shopping-lists/{shopping_list_id}")
def shopping_list(shopping_list_id: UUID) -> dict[str, Any]:
    try:
        with connect() as conn:
            return get_shopping_list(conn, shopping_list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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


class CookRequest(BaseModel):
    # Optional partial-use overrides: ingredient_id -> actual quantity used.
    overrides: dict[UUID, Decimal] | None = None


class DeductionOut(BaseModel):
    ingredient_id: UUID
    unit: str
    amount: Decimal


class CookResponse(BaseModel):
    meal_id: UUID
    mode: str
    deductions: list[DeductionOut]


@app.post("/v1/meals/{meal_id}/cook", response_model=CookResponse)
def cook(meal_id: UUID, req: CookRequest | None = None) -> CookResponse:
    """Mark a meal cooked and deplete the pantry per the household mode (spec §3.4)."""
    overrides = req.overrides if req else None
    try:
        with connect() as conn:
            result = cook_meal(conn, meal_id, overrides)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    return CookResponse(
        meal_id=result.meal_id,
        mode=result.mode,
        deductions=[
            DeductionOut(ingredient_id=d.ingredient_id, unit=d.unit, amount=d.amount)
            for d in result.deductions
        ],
    )
