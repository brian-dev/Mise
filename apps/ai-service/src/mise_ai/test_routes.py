"""Test-only helper endpoints (mounted only when settings.test_mode).

These exist to make E2E (Playwright) tests fast, cheap, and deterministic: they
let a test reach app states (a household with a ready meal plan) instantly,
WITHOUT calling Claude, and clean up afterward. They require auth like every
other endpoint, so a test signs up a user, gets a token, and seeds for that user.

NEVER enable test mode in production (these mutate/delete data freely).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import current_user
from .db import connect, create_household, persist_meal_plan
from .schemas import (
    GeneratedDay,
    GeneratedIngredient,
    GeneratedMeal,
    GeneratedMealPlan,
    GeneratedRecipe,
    MealPlanRequest,
    MealType,
    Unit,
)

router = APIRouter(prefix="/v1/test", tags=["test"])


class SeedResponse(BaseModel):
    household_id: UUID
    meal_plan_id: UUID
    meal_id: UUID


def _deterministic_plan(household_id: UUID) -> tuple[MealPlanRequest, GeneratedMealPlan]:
    # Date the plan starting today so the meal is "upcoming" on the dashboard
    # (which only surfaces uncooked meals from today forward). Deterministic in
    # content, just not in calendar date.
    today = date.today()
    req = MealPlanRequest(
        household_id=household_id,
        start_date=today,
        end_date=today,
        household_size=2,
        meal_types=[MealType.dinner],
        budget=40,
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date=today,
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner,
                        servings=2,
                        recipe=GeneratedRecipe(
                            title="E2E Test Dinner",
                            cuisine_tags=["american"],
                            default_servings=2,
                            instructions="Combine and cook.",
                            ingredients=[
                                GeneratedIngredient(
                                    name="yellow onion", quantity=2, unit=Unit.lb
                                ),
                                GeneratedIngredient(name="rice", quantity=1, unit=Unit.lb),
                            ],
                        ),
                    )
                ],
            )
        ]
    )
    return req, plan


@router.post("/seed-plan", response_model=SeedResponse)
def seed_plan(user: UUID | None = Depends(current_user)) -> SeedResponse:
    """Create a household (owned by the caller) + a deterministic draft plan, and
    stock the pantry — no Claude. Returns the ids an E2E test needs."""
    with connect() as conn:
        household_id = create_household(conn, "E2E Household", owner_user_id=user)["id"]
        req, plan = _deterministic_plan(household_id)
        meal_plan_id = persist_meal_plan(conn, plan, req)
        with conn.cursor() as cur:
            cur.execute("select id from ingredients where name = 'Yellow Onion'")
            onion = cur.fetchone()
            if onion is not None:
                cur.execute(
                    "insert into pantry_items (household_id, ingredient_id, quantity, unit) "
                    "values (%s, %s, 1.0, 'lb') on conflict do nothing",
                    (household_id, onion[0]),
                )
            cur.execute(
                "select m.id from meals m join meal_plan_days d on d.id = m.meal_plan_day_id "
                "where d.meal_plan_id = %s",
                (meal_plan_id,),
            )
            meal_id = cur.fetchone()[0]  # type: ignore[index]
        conn.commit()
    return SeedResponse(
        household_id=household_id, meal_plan_id=meal_plan_id, meal_id=meal_id
    )


class ResetResponse(BaseModel):
    deleted_households: int


@router.post("/reset", response_model=ResetResponse)
def reset(user: UUID | None = Depends(current_user)) -> ResetResponse:
    """Delete the caller's owned households (cascades plans/meals/lists/pantry).
    Per-user scope keeps parallel test runs isolated."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            delete from households where id in (
              select household_id from household_members
              where user_id = %s and role = 'owner'
            )
            """,
            (user,),
        )
        deleted = cur.rowcount
        conn.commit()
    return ResetResponse(deleted_households=deleted)
