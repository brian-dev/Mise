"""Integration tests for persistence + canonicalization against a live Postgres.

Runs against the local Supabase stack (config.py default DSN). Skipped if the
database isn't reachable. Everything runs inside one transaction that is rolled
back at the end, so the test leaves no residue.
"""

from __future__ import annotations

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

pytestmark = pytest.mark.db


def _chili() -> GeneratedRecipe:
    return GeneratedRecipe(
        title="Veg Chili",
        cuisine_tags=["american"],
        default_servings=4,
        instructions="Simmer beans, tomato, and onion for 40 minutes.",
        ingredients=[
            # Matches the seeded "Yellow Onion" (canonicalization reuses it).
            GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.unit),
            # Novel ingredient — should be inserted.
            GeneratedIngredient(name="dragon fruit zzz", quantity=1, unit=Unit.unit),
        ],
    )


def test_persist_dedup_and_canonicalize(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Test HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("select count(*) from ingredients")
        ingredients_before = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("select id from ingredients where name = 'Yellow Onion'")
        seeded_onion_id = cur.fetchone()[0]  # type: ignore[index]

    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-11",  # type: ignore[arg-type]
        household_size=4,
        meal_types=[MealType.dinner],
    )
    # Same recipe both days → should be stored once and shared.
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, recipe=_chili())],
            ),
            GeneratedDay(
                date="2026-06-11",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, recipe=_chili())],
            ),
        ]
    )

    meal_plan_id = persist_meal_plan(conn, plan, req)

    with conn.cursor() as cur:
        # Plan structure.
        cur.execute("select count(*) from meal_plan_days where meal_plan_id = %s", (meal_plan_id,))
        assert cur.fetchone()[0] == 2  # type: ignore[index]
        cur.execute(
            """
            select count(*) from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            where d.meal_plan_id = %s
            """,
            (meal_plan_id,),
        )
        assert cur.fetchone()[0] == 2  # type: ignore[index]

        # Recipe de-dup: both meals point at one shared recipe.
        cur.execute(
            """
            select count(distinct m.recipe_id) from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            where d.meal_plan_id = %s
            """,
            (meal_plan_id,),
        )
        assert cur.fetchone()[0] == 1  # type: ignore[index]

        # Canonicalization: "yellow onion" reused the seeded row; only the novel
        # ingredient was inserted (+1).
        cur.execute("select count(*) from ingredients")
        assert cur.fetchone()[0] == ingredients_before + 1  # type: ignore[index]
        cur.execute(
            """
            select ri.ingredient_id from recipe_ingredients ri
            join ingredients i on i.id = ri.ingredient_id
            where lower(i.name) = 'yellow onion'
            """
        )
        assert cur.fetchone()[0] == seeded_onion_id  # type: ignore[index]
