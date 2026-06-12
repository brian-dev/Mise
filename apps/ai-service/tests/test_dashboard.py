"""Integration tests for the home-dashboard read model (UX_DESIGN.md).

Runs against the local Supabase stack inside a rolled-back transaction. Covers
the plan summary, upcoming-meal selection, and the three alert buckets
(use_soon / running_low / needed_not_stocked).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import psycopg
import pytest

from mise_ai.dashboard import build_dashboard
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

pytestmark = pytest.mark.db


def _ingredient(cur: psycopg.Cursor, name: str, category: str) -> UUID:
    cur.execute(
        "insert into ingredients (name, category) values (%s, %s) "
        "on conflict (name) do update set category = excluded.category returning id",
        (name, category),
    )
    return cur.fetchone()[0]  # type: ignore[index]


def _stock(
    cur: psycopg.Cursor,
    household_id: UUID,
    ingredient_id: UUID,
    qty: str,
    *,
    days_ago: int = 0,
) -> None:
    cur.execute(
        "insert into pantry_items (household_id, ingredient_id, quantity, unit, added_at) "
        "values (%s, %s, %s, 'lb', now() - make_interval(days => %s))",
        (household_id, ingredient_id, qty, days_ago),
    )


def _household(cur: psycopg.Cursor) -> UUID:
    cur.execute("insert into households (name) values ('Dash HH') returning id")
    return cur.fetchone()[0]  # type: ignore[index]


def _plan_needing(
    conn: psycopg.Connection, household_id: UUID, ingredient_name: str
) -> UUID:
    """A 1-meal plan dated tomorrow whose recipe requires `ingredient_name`."""
    tomorrow = date.today() + timedelta(days=1)
    req = MealPlanRequest(
        household_id=household_id,
        start_date=tomorrow,  # type: ignore[arg-type]
        end_date=tomorrow,  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    recipe = GeneratedRecipe(
        title="Garlic Stew",
        cuisine_tags=["french"],
        default_servings=2,
        instructions="Simmer.",
        ingredients=[GeneratedIngredient(name=ingredient_name, quantity=2, unit=Unit.lb)],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date=tomorrow,  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=recipe)],
            )
        ]
    )
    return persist_meal_plan(conn, plan, req)


def test_dashboard_summarizes_plan_and_upcoming(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id = _household(cur)
    _plan_needing(conn, household_id, "Garlic")

    dash = build_dashboard(conn, household_id)
    assert dash["plan"] is not None
    assert dash["plan"]["meals_total"] == 1
    assert dash["plan"]["meals_cooked"] == 0
    titles = [m["recipe_title"] for m in dash["upcoming_meals"]]
    assert titles == ["Garlic Stew"]


def test_use_soon_flags_perishables_near_expiry(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id = _household(cur)
        # meat shelf life = 4 days; added 3 days ago -> expires in ~1 day (within window).
        meat = _ingredient(cur, "Test Chicken", "meat")
        _stock(cur, household_id, meat, "2.0", days_ago=3)
        # produce shelf life = 7 days; added today -> not near expiry.
        produce = _ingredient(cur, "Test Kale", "produce")
        _stock(cur, household_id, produce, "2.0", days_ago=0)

    dash = build_dashboard(conn, household_id)
    names = [a["name"] for a in dash["alerts"]["use_soon"]]
    assert "Test Chicken" in names
    assert "Test Kale" not in names


def test_running_low_flags_small_quantities(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id = _household(cur)
        low = _ingredient(cur, "Test Salt", "pantry staple")
        _stock(cur, household_id, low, "0.5")  # <= threshold (1.0)
        plenty = _ingredient(cur, "Test Flour", "pantry staple")
        _stock(cur, household_id, plenty, "5.0")

    dash = build_dashboard(conn, household_id)
    names = [a["name"] for a in dash["alerts"]["running_low"]]
    assert "Test Salt" in names
    assert "Test Flour" not in names


def test_needed_not_stocked_lists_missing_plan_ingredients(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        household_id = _household(cur)
    _plan_needing(conn, household_id, "Garlic")  # Garlic required, not in pantry

    dash = build_dashboard(conn, household_id)
    names = [a["name"] for a in dash["alerts"]["needed_not_stocked"]]
    assert "garlic" in [n.lower() for n in names]


def test_needed_not_stocked_excludes_stocked(conn: psycopg.Connection) -> None:
    # Unique name (not in the seed catalog) so the pantry row and the recipe
    # ingredient canonicalize to the same catalog id.
    with conn.cursor() as cur:
        household_id = _household(cur)
        garlic = _ingredient(cur, "test garlic", "produce")
        _stock(cur, household_id, garlic, "3.0")
    _plan_needing(conn, household_id, "test garlic")

    dash = build_dashboard(conn, household_id)
    names = [a["name"].lower() for a in dash["alerts"]["needed_not_stocked"]]
    assert "test garlic" not in names


def test_empty_household_has_no_plan(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        household_id = _household(cur)
    dash = build_dashboard(conn, household_id)
    assert dash["plan"] is None
    assert dash["upcoming_meals"] == []
    assert dash["alerts"]["needed_not_stocked"] == []
