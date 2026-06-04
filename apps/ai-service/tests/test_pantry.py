"""Integration tests for pantry depletion on cook (spec §3.4).

Runs against the local Supabase stack inside a rolled-back transaction.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import connect, persist_meal_plan
from mise_ai.pantry import cook_meal
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


def _setup_plan(cur: psycopg.Cursor, mode: str) -> tuple[UUID, UUID, UUID]:
    """Create a household (with given depletion mode) + a 1-meal plan.

    Returns (household_id, meal_id, onion_id). Recipe: 2 lb yellow onion,
    default_servings 4, meal servings 2 -> factor 0.5 -> deduct 1.0 lb.
    """
    cur.execute(
        "insert into households (name, pantry_depletion_mode) values ('Cook HH', %s) returning id",
        (mode,),
    )
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
        default_servings=4,
        instructions="Simmer.",
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.lb)],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=recipe)],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn_from(cur), plan, req)
    cur.execute(
        """
        select m.id from meals m
        join meal_plan_days d on d.id = m.meal_plan_day_id
        where d.meal_plan_id = %s
        """,
        (meal_plan_id,),
    )
    meal_id = cur.fetchone()[0]  # type: ignore[index]
    return household_id, meal_id, onion_id


def conn_from(cur: psycopg.Cursor) -> psycopg.Connection:
    return cur.connection


def _stock_pantry(cur: psycopg.Cursor, household_id: UUID, onion_id: UUID, qty: str) -> None:
    cur.execute(
        "insert into pantry_items (household_id, ingredient_id, quantity, unit) "
        "values (%s, %s, %s, 'lb')",
        (household_id, onion_id, qty),
    )


def test_auto_deducts_scaled_amount(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id, meal_id, onion_id = _setup_plan(cur, "auto")
        _stock_pantry(cur, household_id, onion_id, "3.0")  # 3 lb on hand

    result = cook_meal(conn, meal_id)
    assert result.mode == "auto"
    assert len(result.deductions) == 1
    assert result.deductions[0].amount == Decimal("1.0")  # 2 lb * (2/4)

    with conn.cursor() as cur:
        cur.execute(
            "select quantity from pantry_items where household_id = %s and ingredient_id = %s",
            (household_id, onion_id),
        )
        assert cur.fetchone()[0] == Decimal("2.000")  # 3 - 1
        cur.execute("select cooked_at from meals where id = %s", (meal_id,))
        assert cur.fetchone()[0] is not None


def test_manual_marks_cooked_without_deducting(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id, meal_id, onion_id = _setup_plan(cur, "manual")
        _stock_pantry(cur, household_id, onion_id, "3.0")

    result = cook_meal(conn, meal_id)
    assert result.mode == "manual"
    assert result.deductions == []

    with conn.cursor() as cur:
        cur.execute(
            "select quantity from pantry_items where household_id = %s and ingredient_id = %s",
            (household_id, onion_id),
        )
        assert cur.fetchone()[0] == Decimal("3.000")  # untouched
        cur.execute("select cooked_at from meals where id = %s", (meal_id,))
        assert cur.fetchone()[0] is not None


def test_override_replaces_computed_amount(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id, meal_id, onion_id = _setup_plan(cur, "auto")
        _stock_pantry(cur, household_id, onion_id, "3.0")

    result = cook_meal(conn, meal_id, overrides={onion_id: Decimal("0.5")})
    assert result.deductions[0].amount == Decimal("0.5")
    with conn.cursor() as cur:
        cur.execute(
            "select quantity from pantry_items where household_id = %s and ingredient_id = %s",
            (household_id, onion_id),
        )
        assert cur.fetchone()[0] == Decimal("2.500")  # 3 - 0.5


def test_already_cooked_raises(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id, meal_id, onion_id = _setup_plan(cur, "auto")
        _stock_pantry(cur, household_id, onion_id, "3.0")
    cook_meal(conn, meal_id)
    with pytest.raises(ValueError, match="already cooked"):
        cook_meal(conn, meal_id)
