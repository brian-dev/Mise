"""Integration test for purchase -> pantry restock (spec §3.5).

Runs against the local Supabase stack inside a rolled-back transaction.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import connect, persist_meal_plan
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
from mise_ai.shopping import build_shopping_list, mark_purchased

pytestmark = pytest.mark.db


@pytest.fixture
def conn() -> psycopg.Connection:  # type: ignore[misc]
    try:
        c = connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local Postgres not reachable: {e}")
    c.autocommit = False
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _onion_qty(cur: psycopg.Cursor, household_id: UUID, onion_id: UUID) -> Decimal | None:
    cur.execute(
        "select quantity from pantry_items "
        "where household_id = %s and ingredient_id = %s and unit = 'lb'",
        (household_id, onion_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def test_purchase_restocks_pantry(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Buy HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("select id from ingredients where name = 'Yellow Onion'")
        onion_id = cur.fetchone()[0]  # type: ignore[index]
        # Start with 1 lb on hand.
        cur.execute(
            "insert into pantry_items (household_id, ingredient_id, quantity, unit) "
            "values (%s, %s, 1.0, 'lb')",
            (household_id, onion_id),
        )

    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=4,
        meal_types=[MealType.dinner],
    )
    recipe = GeneratedRecipe(
        title="Onion Soup",
        cuisine_tags=["french"],
        default_servings=4,
        instructions="Simmer.",
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=3, unit=Unit.lb)],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=4, recipe=recipe)],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)

    # Required 3 lb − 1 lb pantry = 2 lb on the list.
    summary = build_shopping_list(conn, meal_plan_id)
    assert summary.items_total == 1

    result = mark_purchased(conn, summary.shopping_list_id)
    assert len(result.restocked) == 1
    assert result.restocked[0].amount == Decimal("2.000")

    with conn.cursor() as cur:
        # 1 lb on hand + 2 lb purchased = 3 lb.
        assert _onion_qty(cur, household_id, onion_id) == Decimal("3.000")
        cur.execute("select status from shopping_lists where id = %s", (summary.shopping_list_id,))
        assert cur.fetchone()[0] == "purchased"  # type: ignore[index]

    # Double-purchase is rejected (no double restock).
    with pytest.raises(ValueError, match="already purchased"):
        mark_purchased(conn, summary.shopping_list_id)
