"""Interactive shopping-list item mutations (check / add / delete / quantity).

DB-marked; runs against the local stack inside a rolled-back transaction.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import (
    add_manual_item,
    delete_item,
    get_shopping_list,
    persist_meal_plan,
    set_item_checked,
    update_item_quantity,
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


def _list_with_one_item(conn: psycopg.Connection) -> UUID:
    """Build a shopping list with a single priced onion line; return its id."""
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Items HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=4,
        meal_types=[MealType.dinner],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner,
                        servings=4,
                        recipe=GeneratedRecipe(
                            title="Onion Stew",
                            cuisine_tags=["american"],
                            default_servings=4,
                            instructions="Cook.",
                            ingredients=[
                                GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.lb)
                            ],
                        ),
                    )
                ],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)
    return build_shopping_list(conn, meal_plan_id).shopping_list_id


def test_get_shopping_list_exposes_id_and_category(conn: psycopg.Connection) -> None:
    sl = _list_with_one_item(conn)
    item = get_shopping_list(conn, sl)["items"][0]
    assert item["id"] is not None
    assert item["category"] == "produce"  # Yellow Onion is seeded as produce
    assert item["is_checked"] is False
    assert item["source"] == "recipe"


def test_check_and_uncheck(conn: psycopg.Connection) -> None:
    sl = _list_with_one_item(conn)
    item_id = get_shopping_list(conn, sl)["items"][0]["id"]

    set_item_checked(conn, sl, item_id, True)
    assert get_shopping_list(conn, sl)["items"][0]["is_checked"] is True
    set_item_checked(conn, sl, item_id, False)
    assert get_shopping_list(conn, sl)["items"][0]["is_checked"] is False


def test_update_quantity(conn: psycopg.Connection) -> None:
    sl = _list_with_one_item(conn)
    item_id = get_shopping_list(conn, sl)["items"][0]["id"]
    update_item_quantity(conn, sl, item_id, Decimal("3.0"))
    assert get_shopping_list(conn, sl)["items"][0]["quantity_needed"] == Decimal("3.000")


def test_add_manual_item(conn: psycopg.Connection) -> None:
    sl = _list_with_one_item(conn)
    created = add_manual_item(conn, sl, "paper towels", Decimal("2"), "unit")
    assert created["source"] == "manual"
    assert created["estimated_price"] is None

    items = get_shopping_list(conn, sl)["items"]
    names = {i["name"] for i in items}
    assert "paper towels" in names
    assert len(items) == 2


def test_delete_item_recomputes_total(conn: psycopg.Connection) -> None:
    sl = _list_with_one_item(conn)
    before = get_shopping_list(conn, sl)
    assert before["estimated_total"] == Decimal("1.80")  # 2 lb * 0.90

    item_id = before["items"][0]["id"]
    delete_item(conn, sl, item_id)

    after = get_shopping_list(conn, sl)
    assert after["items"] == []
    assert after["estimated_total"] == Decimal("0")  # recomputed
