"""AI pricing fallback: offline (stubbed Claude) + a db test for applying
estimates + an opt-in live test (real Claude)."""

from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

import mise_ai.pricing as pricing_mod
from mise_ai.anthropic_client import ToolCallResult, Usage
from mise_ai.db import create_household, persist_meal_plan
from mise_ai.pricing import PricingError, PricingItem, estimate_prices
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
from mise_ai.shopping import (
    apply_estimated_prices,
    build_shopping_list,
    get_unpriced_items,
)


def _stub(monkeypatch, prices: list[float]) -> None:
    def fake_call_tool(**_kw: object) -> ToolCallResult:
        return ToolCallResult(
            tool_input={"prices": [{"estimated_price": p} for p in prices]},
            usage=Usage(5, 5, 0, 0),
            raw_content=[],
        )

    monkeypatch.setattr(pricing_mod, "call_tool", fake_call_tool)


def test_estimate_prices_maps_in_order(monkeypatch) -> None:
    _stub(monkeypatch, [1.25, 0.5])
    items = [
        PricingItem("garlic", Decimal("2"), "clove"),
        PricingItem("canned tomatoes", Decimal("1"), "can"),
    ]
    res = estimate_prices(items)
    assert res.prices == [Decimal("1.25"), Decimal("0.50")]


def test_estimate_prices_length_mismatch_raises(monkeypatch) -> None:
    _stub(monkeypatch, [1.0])  # only one price for two items
    with pytest.raises(PricingError):
        estimate_prices([PricingItem("a", Decimal("1"), "unit"),
                         PricingItem("b", Decimal("1"), "unit")])


def test_empty_items_short_circuits() -> None:
    res = estimate_prices([])
    assert res.prices == []


@pytest.mark.db
def test_unpriced_items_and_apply(conn: psycopg.Connection) -> None:
    household_id = create_household(conn, "Price HH")["id"]
    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-10",  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    recipe = GeneratedRecipe(
        title="Garlic Dish",
        cuisine_tags=["x"],
        default_servings=2,
        instructions="cook",
        # A novel count-unit ingredient -> deterministic path leaves it unpriced.
        ingredients=[GeneratedIngredient(name="exotic spice zzz", quantity=2, unit=Unit.unit)],
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
    summary = build_shopping_list(conn, meal_plan_id)
    assert summary.items_priced == 0  # nothing priced by USDA

    unpriced = get_unpriced_items(conn, summary.shopping_list_id)
    assert len(unpriced) == 1
    assert unpriced[0]["name"] == "exotic spice zzz"

    total = apply_estimated_prices(
        conn, summary.shopping_list_id, [(unpriced[0]["id"], Decimal("2.50"))]  # type: ignore[arg-type]
    )
    assert total == Decimal("2.50")


@pytest.mark.live
def test_live_estimate_prices() -> None:
    items = [
        PricingItem("garlic", Decimal("3"), "clove"),
        PricingItem("canned diced tomatoes", Decimal("1"), "can"),
    ]
    res = estimate_prices(items, region="Texas")
    assert len(res.prices) == 2
    assert all(p > 0 for p in res.prices)  # never zero for real items
