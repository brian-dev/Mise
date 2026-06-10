"""Integration test for the shopping-list builder against a live Postgres.

Runs inside a rolled-back transaction against the local Supabase stack. Verifies
pantry subtraction, USDA pricing (unit-matched), null pricing on unit mismatch,
and budget reconciliation.
"""

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

from mise_ai.db import persist_meal_plan
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


def test_build_shopping_list(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into households (name) values ('Shop HH') returning id"
        )
        household_id = cur.fetchone()[0]  # type: ignore[index]
        # Seeded "Yellow Onion" is priced at 0.90 / lb.
        cur.execute("select id from ingredients where name = 'Yellow Onion'")
        onion_id = cur.fetchone()[0]  # type: ignore[index]

    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=4,
        meal_types=[MealType.dinner],
        budget=1.00,  # below the expected total -> over budget
    )
    recipe = GeneratedRecipe(
        title="Onion Stew",
        cuisine_tags=["american"],
        default_servings=4,
        instructions="Cook.",
        ingredients=[
            # lb matches usda_unit -> priced
            GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.lb),
            # novel + count unit -> unpriced
            GeneratedIngredient(name="star anise zzz", quantity=3, unit=Unit.unit),
        ],
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

    # Pantry already has 0.5 lb onion -> needed = 2 - 0.5 = 1.5 lb.
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into pantry_items (household_id, ingredient_id, quantity, unit)
            values (%s, %s, 0.5, 'lb')
            """,
            (household_id, onion_id),
        )

    result = build_shopping_list(conn, meal_plan_id)

    assert result.items_total == 2
    assert result.items_priced == 1  # onion priced; star anise not
    assert result.items_unpriced == 1
    # 1.5 lb * 0.90 = 1.35
    assert result.estimated_total == Decimal("1.35")
    assert result.budget == Decimal("1.00")
    assert result.over_budget is True

    with conn.cursor() as cur:
        cur.execute(
            """
            select quantity_needed, estimated_price from shopping_list_items
            where shopping_list_id = %s and ingredient_id = %s
            """,
            (result.shopping_list_id, onion_id),
        )
        qty, price = cur.fetchone()  # type: ignore[misc]
        assert qty == Decimal("1.500")
        assert price == Decimal("1.35")


def test_pricing_converts_units(conn: psycopg.Connection) -> None:
    """An ingredient bought in oz is priced against a per-lb USDA baseline."""
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Conv HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("select id from ingredients where name = 'Yellow Onion'")
        onion_id = cur.fetchone()[0]  # type: ignore[index]

    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    recipe = GeneratedRecipe(
        title="Onion Soup",
        cuisine_tags=["french"],
        default_servings=2,
        instructions="Cook.",
        # 32 oz onion; usda_unit is lb @ 0.90 -> 32 oz = 2 lb -> $1.80.
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=32, unit=Unit.oz)],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=recipe)],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)
    result = build_shopping_list(conn, meal_plan_id)

    assert result.items_priced == 1  # priced despite oz != lb
    assert result.estimated_total == Decimal("1.80")
    with conn.cursor() as cur:
        cur.execute(
            "select unit, estimated_price from shopping_list_items "
            "where shopping_list_id = %s and ingredient_id = %s",
            (result.shopping_list_id, onion_id),
        )
        unit, price = cur.fetchone()  # type: ignore[misc]
        assert unit == "oz"  # stored in the recipe's unit
        assert price == Decimal("1.80")
