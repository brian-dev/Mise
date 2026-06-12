"""FastAPI application entrypoint.

Scaffold only. The generation endpoints (ARCHITECTURE.md §5, docs/AI_LAYER.md)
are stubbed and will be implemented in the first AI-service feature PR:

    POST /v1/meal-plans/generate   -> job kind "meal_plan"   (async)
    POST /v1/recipes/generate      -> job kind "recipe"       (async)
    POST /v1/recipes/{id}/iterate  -> job kind "recipe_iterate"(async)
    POST /v1/pricing/estimate      -> synchronous
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import current_user, require_membership
from .config import settings
from .db import (
    add_to_pantry,
    connect,
    create_generation_job,
    create_household,
    get_job,
    get_current_consents,
    get_household_profile,
    get_meal_plan,
    get_pantry,
    get_recipe_detail,
    get_recipe_for_prompt,
    get_shopping_list,
    get_user_theme,
    set_recipe_image,
    set_user_theme,
    household_for_meal,
    household_for_meal_plan,
    household_for_shopping_list,
    latest_meal_plan_id,
    list_households,
    log_event,
    onboarding_status,
    meal_swap_context,
    persist_meal_plan,
    record_consent,
    recipes_missing_image_for_plan,
    set_job_status,
    swap_meal_recipe,
    update_household_profile,
)
from .dashboard import build_dashboard
from .generation import GenerationError, generate_meal_plan, generate_recipe
from .openfoodfacts import lookup_product
from .pexels import search_image
from .pantry import cook_meal
from .pricing import PricingError, PricingItem, resolve_prices
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


_THEMES = {"warm", "fresh", "dark"}


class ThemeResponse(BaseModel):
    theme: str | None


class ThemeUpdate(BaseModel):
    theme: str


@app.get("/v1/me/theme", response_model=ThemeResponse)
def get_theme(user: UUID | None = Depends(current_user)) -> ThemeResponse:
    """The signed-in user's saved theme (null if unset / unauthenticated)."""
    if user is None:
        return ThemeResponse(theme=None)
    with connect() as conn:
        return ThemeResponse(theme=get_user_theme(conn, user))


@app.put("/v1/me/theme", response_model=ThemeResponse)
def put_theme(
    req: ThemeUpdate, user: UUID | None = Depends(current_user)
) -> ThemeResponse:
    """Persist the user's theme choice to their profile (follows across devices)."""
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if req.theme not in _THEMES:
        raise HTTPException(status_code=422, detail=f"unknown theme {req.theme!r}")
    with connect() as conn:
        set_user_theme(conn, user, req.theme)
    return ThemeResponse(theme=req.theme)


# --------------------------------------------------------------------------- #
# Onboarding: household profile, consent ledger, analytics events.
# --------------------------------------------------------------------------- #
_CONSENT_KINDS = {"personalization", "analytics", "data_sharing", "marketing"}


class OnboardingStatus(BaseModel):
    needs_onboarding: bool
    household_id: UUID | None


@app.get("/v1/me/onboarding", response_model=OnboardingStatus)
def me_onboarding(user: UUID | None = Depends(current_user)) -> OnboardingStatus:
    """Whether the signed-in user should see the onboarding wizard."""
    if user is None:
        return OnboardingStatus(needs_onboarding=False, household_id=None)
    with connect() as conn:
        s = onboarding_status(conn, user)
    return OnboardingStatus(**s)


class HouseholdProfile(BaseModel):
    # All optional — the onboarding wizard fills these progressively.
    household_size: int | None = Field(default=None, ge=1)
    weekly_budget: Decimal | None = None
    preferred_cuisines: list[str] | None = None
    preferred_meal_types: list[str] | None = None
    cooking_time: str | None = None
    dietary_flags: list[str] | None = None
    avoid_text: str | None = None
    region: str | None = None
    store_preference: str | None = None


class HouseholdProfileOut(HouseholdProfile):
    name: str
    onboarding_completed_at: str | None = None


class ProfileUpdate(HouseholdProfile):
    # Stamp onboarding_completed_at when the wizard finishes.
    complete_onboarding: bool = False


@app.get("/v1/households/{household_id}/profile", response_model=HouseholdProfileOut)
def get_profile(
    household_id: UUID, user: UUID | None = Depends(current_user)
) -> HouseholdProfileOut:
    with connect() as conn:
        require_membership(conn, user, household_id)
        try:
            p = get_household_profile(conn, household_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    completed = p.pop("onboarding_completed_at")
    return HouseholdProfileOut(
        **p, onboarding_completed_at=completed.isoformat() if completed else None
    )


@app.put("/v1/households/{household_id}/profile", status_code=204)
def put_profile(
    household_id: UUID, req: ProfileUpdate, user: UUID | None = Depends(current_user)
) -> None:
    """Persist the household onboarding snapshot. Only provided fields are written;
    `complete_onboarding` stamps completion and logs the event."""
    fields = req.model_dump(exclude={"complete_onboarding"}, exclude_none=True)
    with connect() as conn:
        require_membership(conn, user, household_id)
        update_household_profile(
            conn, household_id, fields, complete_onboarding=req.complete_onboarding
        )
        if req.complete_onboarding:
            log_event(
                conn,
                "onboarding_completed",
                user_id=user,
                household_id=household_id,
                properties={"fields": sorted(fields.keys())},
            )


class ConsentDecision(BaseModel):
    kind: str
    granted: bool


class ConsentUpdate(BaseModel):
    version: str
    decisions: list[ConsentDecision]


@app.get("/v1/me/consents")
def get_consents(user: UUID | None = Depends(current_user)) -> dict[str, bool]:
    if user is None:
        return {}
    with connect() as conn:
        return get_current_consents(conn, user)


@app.post("/v1/me/consents", status_code=204)
def post_consents(
    req: ConsentUpdate, user: UUID | None = Depends(current_user)
) -> None:
    """Append consent decisions to the ledger (one row each, history-preserving)."""
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    unknown = {d.kind for d in req.decisions} - _CONSENT_KINDS
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown consent kind(s): {unknown}")
    with connect() as conn:
        for d in req.decisions:
            record_consent(conn, user, d.kind, d.granted, req.version)


class EventIn(BaseModel):
    event_type: str
    household_id: UUID | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/events", status_code=204)
def post_event(req: EventIn, user: UUID | None = Depends(current_user)) -> None:
    """Client-emitted analytics event. Auth-scoped; household membership checked
    when a household is named so callers can't attribute events elsewhere."""
    with connect() as conn:
        if req.household_id is not None:
            require_membership(conn, user, req.household_id)
        log_event(
            conn,
            req.event_type,
            user_id=user,
            household_id=req.household_id,
            properties=req.properties,
        )


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


class ProductResponse(BaseModel):
    barcode: str
    name: str
    brand: str | None
    quantity: str | None
    price: Decimal | None  # USD from Open Prices, if available


@app.get("/v1/products/{barcode}", response_model=ProductResponse)
def product(barcode: str, user: UUID | None = Depends(current_user)) -> ProductResponse:
    """Resolve a scanned barcode to a product (Open Food Facts) + crowd price
    (Open Prices, USD if available). Auth only; not household-scoped."""
    p = lookup_product(barcode)
    if p is None:
        raise HTTPException(status_code=404, detail=f"no product for barcode {barcode}")
    return ProductResponse(
        barcode=p.barcode, name=p.name, brand=p.brand, quantity=p.quantity, price=p.price
    )


class AddBarcodeRequest(BaseModel):
    barcode: str
    quantity: Decimal = Decimal("1")
    unit: Unit = Unit.unit


class AddBarcodeResponse(BaseModel):
    ingredient_id: UUID
    name: str
    quantity: Decimal
    unit: str


@app.post("/v1/households/{household_id}/pantry/add-barcode", response_model=AddBarcodeResponse)
def add_pantry_barcode(
    household_id: UUID,
    req: AddBarcodeRequest,
    user: UUID | None = Depends(current_user),
) -> AddBarcodeResponse:
    """Scan-to-pantry (spec §3.4): resolve the barcode to a product name, add it to
    the household pantry as a canonicalized ingredient."""
    with connect() as conn:
        require_membership(conn, user, household_id)
        p = lookup_product(req.barcode)
        if p is None:
            raise HTTPException(
                status_code=404, detail=f"no product for barcode {req.barcode}"
            )
        result = add_to_pantry(conn, household_id, p.name, req.quantity, req.unit.value)
    return AddBarcodeResponse(
        ingredient_id=result["ingredient_id"],
        name=result["name"],
        quantity=req.quantity,
        unit=req.unit.value,
    )


@app.get("/v1/households/{household_id}/dashboard")
def dashboard(
    household_id: UUID, user: UUID | None = Depends(current_user)
) -> dict[str, Any]:
    """Home-dashboard read model (UX_DESIGN.md): current plan summary, upcoming
    meals, and ingredient alerts (use-soon / running-low / needed-not-stocked)."""
    with connect() as conn:
        require_membership(conn, user, household_id)
        return build_dashboard(conn, household_id)


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


class RecipeIngredientOut(BaseModel):
    name: str
    quantity: Decimal
    unit: str
    is_optional: bool


class RecipeDetail(BaseModel):
    recipe_id: UUID
    title: str
    description: str | None
    cuisine_tags: list[str]
    prep_time: int | None
    cook_time: int | None
    default_servings: int
    instructions: str | None
    image_url: str | None
    ingredients: list[RecipeIngredientOut]


@app.get("/v1/recipes/{recipe_id}", response_model=RecipeDetail)
def recipe(recipe_id: UUID, user: UUID | None = Depends(current_user)) -> RecipeDetail:
    """Full recipe for the detail screen. Recipes live in a shared pool, so this is
    auth-only (not household-scoped). On first view, lazily resolves a
    representative photo (Pexels, keyed title→cuisine) and stores it."""
    try:
        with connect() as conn:
            detail = get_recipe_detail(conn, recipe_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if detail["image_url"] is None:
        cuisine = detail["cuisine_tags"][0] if detail["cuisine_tags"] else ""
        image_url = search_image(detail["title"], f"{cuisine} food".strip(), "food")
        if image_url:
            with connect() as conn:
                set_recipe_image(conn, recipe_id, image_url)
            detail["image_url"] = image_url

    return RecipeDetail(**detail)


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


def _populate_plan_images(meal_plan_id: UUID) -> None:
    """Resolve + store a representative photo for each of a plan's recipes that
    lacks one (Pexels, keyed title→cuisine). Best-effort and parallel; any failure
    is ignored so a missing image never affects the plan. No-op without a key."""
    with connect() as conn:
        recipes = recipes_missing_image_for_plan(conn, meal_plan_id)
    if not recipes:
        return

    def resolve(rec: dict[str, Any]) -> tuple[UUID, str | None]:
        cuisine = rec["cuisine_tags"][0] if rec["cuisine_tags"] else ""
        return rec["id"], search_image(rec["title"], f"{cuisine} food".strip(), "food")

    with ThreadPoolExecutor(max_workers=settings.parallel_max_workers) as pool:
        results = list(pool.map(resolve, recipes))

    pairs = [(rid, url) for rid, url in results if url]
    if pairs:
        with connect() as conn:
            for rid, url in pairs:
                set_recipe_image(conn, rid, url)


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
        # Best-effort: fetch representative photos so the plan/cards have images on
        # first load. Never let this fail the job.
        try:
            _populate_plan_images(meal_plan_id)
        except Exception:  # noqa: BLE001
            pass
        # Best-effort analytics: record that a plan was generated.
        try:
            days = (req.end_date - req.start_date).days + 1
            with connect() as conn:
                log_event(
                    conn,
                    "plan_generated",
                    household_id=req.household_id,
                    properties={
                        "days": days,
                        "meal_types": [m.value for m in req.meal_types],
                        "cuisines": req.cuisines,
                        "budget": float(req.budget) if req.budget is not None else None,
                        "household_size": req.household_size,
                    },
                )
        except Exception:  # noqa: BLE001
            pass
        with connect() as conn:
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
    sources: dict[str, int]  # e.g. {"spoonacular": 3, "ai": 1}


@app.post(
    "/v1/shopping-lists/{shopping_list_id}/estimate-prices",
    response_model=EstimatePricesResponse,
)
def estimate_list_prices(
    shopping_list_id: UUID, user: UUID | None = Depends(current_user)
) -> EstimatePricesResponse:
    """Fill in prices for items the USDA path couldn't price (ARCHITECTURE §7):
    paid-tier Spoonacular first (when configured), AI estimate for the rest. Only
    touches items still missing a price."""
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
            sources={},
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
        result = resolve_prices(pricing_items, region=region, store=store)
    except PricingError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    priced = [
        (UUID(str(it["id"])), price) for it, price in zip(items, result.prices, strict=True)
    ]
    with connect() as conn:
        total = apply_estimated_prices(conn, shopping_list_id, priced)
    sources: dict[str, int] = {}
    for s in result.sources:
        sources[s] = sources.get(s, 0) + 1
    return EstimatePricesResponse(
        shopping_list_id=shopping_list_id,
        estimated_total=total,
        items_estimated=len(priced),
        sources=sources,
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


class IterateRequest(BaseModel):
    modify: str  # required — how to change the dish ("spicier", "make it vegan")
    dietary: Dietary | None = None


@app.post("/v1/meals/{meal_id}/iterate", response_model=SwapResponse)
def iterate(
    meal_id: UUID, req: IterateRequest, user: UUID | None = Depends(current_user)
) -> SwapResponse:
    """Produce a *variant* of the meal's current recipe per `modify` (AI_LAYER §8) —
    keeps the dish's essence, unlike swap which replaces it. Points the meal at the
    new recipe."""
    with connect() as conn:
        try:
            ctx = meal_swap_context(conn, meal_id)
            base_recipe = get_recipe_for_prompt(conn, ctx["recipe_id"])
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
            dietary=(req.dietary if req.dietary else Dietary()),
            pantry=pantry,
            avoid_titles=ctx["avoid_titles"],
            modify=req.modify,
        )
        try:
            result = generate_recipe(recipe_req, base_recipe=base_recipe)
        except GenerationError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        recipe_id = swap_meal_recipe(conn, meal_id, result.recipe)

    return SwapResponse(
        meal_id=meal_id,
        recipe_id=recipe_id,
        title=result.recipe.title,
        cuisine_tags=result.recipe.cuisine_tags,
    )
