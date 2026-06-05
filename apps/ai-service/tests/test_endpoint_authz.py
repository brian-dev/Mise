"""Household resolvers for parent-scoped resources + cross-member rejection.

Verifies that meal-plan / shopping-list / meal ids resolve to the owning
household, and that a non-member is rejected. Live Postgres, rolled back.
"""

from __future__ import annotations

import uuid
from uuid import UUID

import psycopg
import pytest
from fastapi import HTTPException

from mise_ai.auth import require_membership
from mise_ai.db import (
    create_household,
    household_for_meal,
    household_for_meal_plan,
    household_for_shopping_list,
    persist_meal_plan,
)
from mise_ai.schemas import (
    GeneratedDay,
    GeneratedIngredient,
    GeneratedMeal,
    GeneratedMealPlan,
    GeneratedRecipe,
    MealPlanRequest,
    MealType,
    Unit,
)
from mise_ai.shopping import build_shopping_list

pytestmark = pytest.mark.db


def _make_user(cur: psycopg.Cursor, email: str) -> UUID:
    uid = uuid.uuid4()
    cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, email))
    return uid


def test_resolvers_and_cross_member_rejection(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        alice = _make_user(cur, f"alice-{uuid.uuid4()}@t.dev")
        bob = _make_user(cur, f"bob-{uuid.uuid4()}@t.dev")
    household_id = create_household(conn, "Alice HH", owner_user_id=alice)["id"]

    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner,
                        recipe=GeneratedRecipe(
                            title="Soup",
                            cuisine_tags=["x"],
                            default_servings=2,
                            instructions="cook",
                            ingredients=[
                                GeneratedIngredient(name="yellow onion", quantity=1, unit=Unit.lb)
                            ],
                        ),
                    )
                ],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)
    shopping = build_shopping_list(conn, meal_plan_id)
    with conn.cursor() as cur:
        cur.execute(
            "select m.id from meals m join meal_plan_days d on d.id = m.meal_plan_day_id "
            "where d.meal_plan_id = %s",
            (meal_plan_id,),
        )
        meal_id = cur.fetchone()[0]  # type: ignore[index]

    # All three resolvers point back at Alice's household.
    assert household_for_meal_plan(conn, meal_plan_id) == household_id
    assert household_for_shopping_list(conn, shopping.shopping_list_id) == household_id
    assert household_for_meal(conn, meal_id) == household_id

    # Bob (non-member) is rejected for each resolved household; Alice passes.
    for hid in (
        household_for_meal_plan(conn, meal_plan_id),
        household_for_shopping_list(conn, shopping.shopping_list_id),
        household_for_meal(conn, meal_id),
    ):
        require_membership(conn, alice, hid)  # no raise
        with pytest.raises(HTTPException) as ei:
            require_membership(conn, bob, hid)
        assert ei.value.status_code == 403


def test_resolvers_raise_for_missing(conn: psycopg.Connection) -> None:
    for fn in (household_for_meal_plan, household_for_shopping_list, household_for_meal):
        with pytest.raises(ValueError):
            fn(conn, uuid.uuid4())
