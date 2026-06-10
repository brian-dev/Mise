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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .auth import current_user, require_membership
from .config import settings
from .db import (
    connect,
    create_generation_job,
    create_household,
    get_job,
    get_meal_plan,
    get_pantry,
    get_shopping_list,
    household_for_meal,
    household_for_meal_plan,
    household_for_shopping_list,
    latest_meal_plan_id,
    list_households,
    meal_swap_context,
    persist_meal_plan,
    set_job_status,
    swap_meal_recipe,
)
from .generation import GenerationError, generate_meal_plan, generate_recipe
from .pantry import cook_meal
from .pricing import PricingError, PricingItem, estimate_prices
from .schemas import Dietary, MealPlanRequest, PantryItem, RecipeRequest, Unit
from .shopping import (
    apply_estimated_prices,
    build_shopping_list,
    get_unpriced_items,
    mark_purchased,
    shopping_list_region_store,
)

app = FastAPI(title="Mise AI Service", version="0.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Test-only helper endpoints (/v1/test/*), mounted only in test mode.
if settings.test_mode:
    from .test_routes import router as test_router

    app.include_router(test_router)


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
def households(user: UUID | None = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as conn:
        return list_households(conn, user)


@app.post("/v1/households")
def new_household(
    req: HouseholdCreate, user: UUID | None = Depends(current_user)
) -> dict[str, Any]:
    with connect() as conn:
        return create_household(conn, req.name, owner_user_id=user)


@app.get("/v1/households/{household_id}/pantry")
def pantry(
    household_id: UUID, user: UUID | None = Depends(current_user)
) -> list[dict[str, Any]]:
    with connect() as conn:
        require_membership(conn, user, household_id)
        return get_pantry(conn, household_id)


@app.get("/v1/households/{household_id}/latest-plan")
def latest_plan(
    household_id: UUID, user: UUID | None = Depends(current_user)
) -> dict[str, Any]:
    """The household's most recent meal plan (404 if none) — lets the UI show an
    existing plan without regenerating."""
    with connect() as conn:
        require_membership(conn, user, household_id)
        pid = latest_meal_plan_id(conn, household_id)
        if pid is None:
            raise HTTPException(status_code=404, detail="no meal plan for this household")
        return get_meal_plan(conn, pid)


@app.get("/v1/meal-plans/{meal_plan_id}")
def meal_plan(
    meal_plan_id: UUID, user: UUID | None = Depends(current_user)
) -> dict[str, Any]:
    try:
        with connect() as conn:
            require_membership(conn, user, household_for_meal_plan(conn, meal_plan_id))
            return get_meal_plan(conn, meal_plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/v1/shopping-lists/{shopping_list_id}")
def shopping_list(
    shopping_list_id: UUID, user: UUID | None = Depends(current_user)
) -> dict[str, Any]:
    try:
        with connect() as conn:
            require_membership(
                conn, user, household_for_shopping_list(conn, shopping_list_id)
            )
            return get_shopping_list(conn, shopping_list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class JobAccepted(BaseModel):
    job_id: UUID
    status: str


class JobStatus(BaseModel):
    id: UUID
    kind: str
    status: str
    result: dict[str, Any] | None
    error: str | None


def _run_meal_plan_job(job_id: UUID, req: MealPlanRequest) -> None:
    """Background worker: generate + persist, updating the job row (ARCHITECTURE §5).

    Catches everything so the job always resolves to done/failed — the client
    polls the row and must never hang.
    """
    try:
        with connect() as conn:
            set_job_status(conn, job_id, "running")
        result = generate_meal_plan(req)
        with connect() as conn:
            meal_plan_id = persist_meal_plan(conn, result.plan, req)
            set_job_status(
                conn,
                job_id,
                "done",
                result={
                    "meal_plan_id": str(meal_plan_id),
                    "repair_attempts": result.repair_attempts,
                    "output_tokens": result.total_output_tokens,
                },
            )
    except Exception as e:  # noqa: BLE001 — surface any failure on the job row
        with connect() as conn:
            set_job_status(conn, job_id, "failed", error=str(e))


@app.post("/v1/meal-plans/generate", status_code=202, response_model=JobAccepted)
def generate(
    req: MealPlanRequest,
    background: BackgroundTasks,
    user: UUID | None = Depends(current_user),
) -> JobAccepted:
    """Queue a meal-plan generation job and return immediately (ARCHITECTURE §5).

    The client polls GET /v1/jobs/{job_id}; on done, result.meal_plan_id points
    at the persisted draft. (Realtime push is a later enhancement.)
    """
    with connect() as conn:
        require_membership(conn, user, req.household_id)
        job_id = create_generation_job(
            conn, req.household_id, "meal_plan", req.model_dump(mode="json"), requested_by=user
        )
    background.add_task(_run_meal_plan_job, job_id, req)
    return JobAccepted(job_id=job_id, status="queued")


@app.get("/v1/jobs/{job_id}", response_model=JobStatus)
def job(job_id: UUID) -> JobStatus:
    try:
        with connect() as conn:
            row = get_job(conn, job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return JobStatus(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        result=row["result"],
        error=row["error"],
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
def build_list(
    req: ShoppingListRequest, user: UUID | None = Depends(current_user)
) -> ShoppingListResponse:
    """Build a draft shopping list from a meal plan (ARCHITECTURE §7, spec §3.5).

    Aggregates required quantities, subtracts the pantry, prices against the USDA
    baseline, and reconciles against the plan budget.
    """
    try:
        with connect() as conn:
            require_membership(conn, user, household_for_meal_plan(conn, req.meal_plan_id))
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


class EstimatePricesResponse(BaseModel):
    shopping_list_id: UUID
    estimated_total: Decimal
    items_estimated: int


@app.post(
    "/v1/shopping-lists/{shopping_list_id}/estimate-prices",
    response_model=EstimatePricesResponse,
)
def estimate_list_prices(
    shopping_list_id: UUID, user: UUID | None = Depends(current_user)
) -> EstimatePricesResponse:
    """Fill in prices for items the USDA path couldn't price, via the AI fallback
    (AI_LAYER §9). Idempotent-ish: only touches items still missing a price."""
    with connect() as conn:
        try:
            require_membership(
                conn, user, household_for_shopping_list(conn, shopping_list_id)
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        items = get_unpriced_items(conn, shopping_list_id)
        region, store = shopping_list_region_store(conn, shopping_list_id)

    if not items:
        with connect() as conn:
            current = get_shopping_list(conn, shopping_list_id)
        return EstimatePricesResponse(
            shopping_list_id=shopping_list_id,
            estimated_total=Decimal(str(current["estimated_total"])),
            items_estimated=0,
        )

    pricing_items = [
        PricingItem(
            name=str(it["name"]),
            quantity=Decimal(str(it["quantity_needed"])),
            unit=str(it["unit"]),
        )
        for it in items
    ]
    try:
        result = estimate_prices(pricing_items, region=region, store=store)
    except PricingError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    priced = [
        (UUID(str(it["id"])), price) for it, price in zip(items, result.prices, strict=True)
    ]
    with connect() as conn:
        total = apply_estimated_prices(conn, shopping_list_id, priced)
    return EstimatePricesResponse(
        shopping_list_id=shopping_list_id,
        estimated_total=total,
        items_estimated=len(priced),
    )


class RestockOut(BaseModel):
    ingredient_id: UUID
    unit: str
    amount: Decimal


class PurchaseResponse(BaseModel):
    shopping_list_id: UUID
    restocked: list[RestockOut]


@app.post("/v1/shopping-lists/{shopping_list_id}/purchase", response_model=PurchaseResponse)
def purchase(
    shopping_list_id: UUID, user: UUID | None = Depends(current_user)
) -> PurchaseResponse:
    """Mark a shopping list purchased and restock the pantry (spec §3.5)."""
    try:
        with connect() as conn:
            require_membership(
                conn, user, household_for_shopping_list(conn, shopping_list_id)
            )
            result = mark_purchased(conn, shopping_list_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return PurchaseResponse(
        shopping_list_id=result.shopping_list_id,
        restocked=[
            RestockOut(ingredient_id=r.ingredient_id, unit=r.unit, amount=r.amount)
            for r in result.restocked
        ],
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
def cook(
    meal_id: UUID,
    req: CookRequest | None = None,
    user: UUID | None = Depends(current_user),
) -> CookResponse:
    """Mark a meal cooked and deplete the pantry per the household mode (spec §3.4)."""
    overrides = req.overrides if req else None
    with connect() as conn:
        try:
            household_id = household_for_meal(conn, meal_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        require_membership(conn, user, household_id)
        try:
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


class SwapRequest(BaseModel):
    dietary: Dietary | None = None
    modify: str | None = None  # e.g. "spicier", "make it vegan"


class SwapResponse(BaseModel):
    meal_id: UUID
    recipe_id: UUID
    title: str
    cuisine_tags: list[str]


@app.post("/v1/meals/{meal_id}/swap", response_model=SwapResponse)
def swap(
    meal_id: UUID,
    req: SwapRequest | None = None,
    user: UUID | None = Depends(current_user),
) -> SwapResponse:
    """Regenerate the recipe for one meal slot and point the meal at it (AI_LAYER §8).

    Synchronous (single recipe, ~seconds). Constrained by dietary + pantry + the
    other meals in the plan for variety.
    """
    with connect() as conn:
        try:
            ctx = meal_swap_context(conn, meal_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        require_membership(conn, user, ctx["household_id"])
        pantry = [
            PantryItem(name=p["name"], quantity=float(p["quantity"]), unit=Unit(p["unit"]))
            for p in get_pantry(conn, ctx["household_id"])
        ]
        recipe_req = RecipeRequest(
            meal_type=ctx["meal_type"],
            servings=ctx["servings"],
            dietary=(req.dietary if req and req.dietary else Dietary()),
            pantry=pantry,
            avoid_titles=ctx["avoid_titles"],
            modify=(req.modify if req else None),
        )
        try:
            result = generate_recipe(recipe_req)
        except GenerationError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        recipe_id = swap_meal_recipe(conn, meal_id, result.recipe)

    return SwapResponse(
        meal_id=meal_id,
        recipe_id=recipe_id,
        title=result.recipe.title,
        cuisine_tags=result.recipe.cuisine_tags,
    )
