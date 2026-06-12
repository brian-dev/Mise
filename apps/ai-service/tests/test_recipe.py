"""Recipe detail read model + image resolution (UX_DESIGN.md §8).

DB-marked tests run against the local stack inside a rolled-back transaction.
Pexels is exercised in pure form (no network): with no key configured it must
degrade to None.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest

from mise_ai import pexels
from mise_ai.config import settings
from mise_ai.db import (
    get_recipe_detail,
    persist_meal_plan,
    recipes_missing_image_for_plan,
    set_recipe_image,
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


def _seed_recipe(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Recipe HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-12",  # type: ignore[arg-type]
        end_date="2026-06-12",  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-12",  # type: ignore[arg-type]
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner,
                        servings=2,
                        recipe=GeneratedRecipe(
                            title="Chana Masala",
                            description="Spiced chickpea curry.",
                            cuisine_tags=["indian"],
                            prep_time=10,
                            cook_time=20,
                            default_servings=2,
                            instructions="Simmer chickpeas in spiced tomato.",
                            ingredients=[
                                GeneratedIngredient(name="chickpeas", quantity=2, unit=Unit.cup),
                                GeneratedIngredient(
                                    name="cilantro", quantity=1, unit=Unit.tbsp, is_optional=True
                                ),
                            ],
                        ),
                    )
                ],
            )
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)
    with conn.cursor() as cur:
        cur.execute(
            """
            select m.recipe_id from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            where d.meal_plan_id = %s
            """,
            (meal_plan_id,),
        )
        return cur.fetchone()[0]  # type: ignore[index]


@pytest.mark.db
def test_get_recipe_detail_returns_full_recipe(conn: psycopg.Connection) -> None:
    recipe_id = _seed_recipe(conn)
    detail = get_recipe_detail(conn, recipe_id)

    assert detail["title"] == "Chana Masala"
    assert detail["cuisine_tags"] == ["indian"]
    assert detail["prep_time"] == 10
    assert detail["image_url"] is None  # not resolved yet
    names = {i["name"] for i in detail["ingredients"]}
    assert names == {"chickpeas", "cilantro"}


@pytest.mark.db
def test_set_recipe_image_persists(conn: psycopg.Connection) -> None:
    recipe_id = _seed_recipe(conn)
    set_recipe_image(conn, recipe_id, "https://example.com/photo.jpg")
    assert get_recipe_detail(conn, recipe_id)["image_url"] == "https://example.com/photo.jpg"


@pytest.mark.db
def test_recipes_missing_image_for_plan(conn: psycopg.Connection) -> None:
    recipe_id = _seed_recipe(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            select d.meal_plan_id from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            where m.recipe_id = %s limit 1
            """,
            (recipe_id,),
        )
        meal_plan_id = cur.fetchone()[0]  # type: ignore[index]

    missing = recipes_missing_image_for_plan(conn, meal_plan_id)
    assert [m["id"] for m in missing] == [recipe_id]

    # Once the image is set, the recipe drops out of the "missing" set.
    set_recipe_image(conn, recipe_id, "https://example.com/p.jpg")
    assert recipes_missing_image_for_plan(conn, meal_plan_id) == []


def test_search_image_without_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pexels_api_key", "")
    assert pexels.search_image("Chana Masala", "indian food") is None


def test_search_image_skips_blank_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pexels_api_key", "")
    # Still None (no key), but importantly does not raise on empty/whitespace.
    assert pexels.search_image("", "   ") is None
