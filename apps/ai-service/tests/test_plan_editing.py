"""Plan editing: single-day regen (DB replace) + remove a meal.

The generation step itself is Claude-backed and covered elsewhere; here we test
the persistence pieces with a fabricated day (no network).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import (
    add_meal_to_day,
    day_regen_context,
    delete_meal,
    get_meal_plan,
    persist_meal_plan,
    replace_day_meals,
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

pytestmark = pytest.mark.db


def _recipe(title: str) -> GeneratedRecipe:
    return GeneratedRecipe(
        title=title,
        cuisine_tags=["american"],
        default_servings=2,
        instructions="Cook.",
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=1, unit=Unit.lb)],
    )


def _two_day_plan(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute("insert into households (name) values ('Edit HH') returning id")
        household_id = cur.fetchone()[0]  # type: ignore[index]
    req = MealPlanRequest(
        household_id=household_id,
        start_date="2026-06-10",  # type: ignore[arg-type]
        end_date="2026-06-11",  # type: ignore[arg-type]
        household_size=2,
        meal_types=[MealType.dinner],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date="2026-06-10",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=_recipe("Day One Dinner"))],
            ),
            GeneratedDay(
                date="2026-06-11",  # type: ignore[arg-type]
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=_recipe("Day Two Dinner"))],
            ),
        ]
    )
    return persist_meal_plan(conn, plan, req)


def test_day_regen_context(conn: psycopg.Connection) -> None:
    plan_id = _two_day_plan(conn)
    ctx = day_regen_context(conn, plan_id, date(2026, 6, 10))
    assert ctx["meal_types"] == ["dinner"]
    assert ctx["servings"] == 2
    # The other day's title is surfaced to bias away from repeats.
    assert ctx["avoid_titles"] == ["Day Two Dinner"]


def test_replace_day_meals(conn: psycopg.Connection) -> None:
    plan_id = _two_day_plan(conn)
    ctx = day_regen_context(conn, plan_id, date(2026, 6, 10))

    new_day = GeneratedDay(
        date="2026-06-10",  # type: ignore[arg-type]
        meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=_recipe("Brand New Dinner"))],
    )
    replace_day_meals(conn, ctx["day_id"], new_day, 2)

    plan = get_meal_plan(conn, plan_id)
    day0 = next(d for d in plan["days"] if d["date"] == date(2026, 6, 10))
    titles = [m["recipe_title"] for m in day0["meals"]]
    assert titles == ["Brand New Dinner"]
    # Day two is untouched.
    day1 = next(d for d in plan["days"] if d["date"] == date(2026, 6, 11))
    assert [m["recipe_title"] for m in day1["meals"]] == ["Day Two Dinner"]


def test_add_meal_to_day(conn: psycopg.Connection) -> None:
    plan_id = _two_day_plan(conn)
    ctx = day_regen_context(conn, plan_id, date(2026, 6, 10))

    add_meal_to_day(conn, ctx["day_id"], "lunch", _recipe("Extra Lunch"), 2)

    plan = get_meal_plan(conn, plan_id)
    day0 = next(d for d in plan["days"] if d["date"] == date(2026, 6, 10))
    by_type = {m["meal_type"]: m["recipe_title"] for m in day0["meals"]}
    assert by_type == {"dinner": "Day One Dinner", "lunch": "Extra Lunch"}


def test_delete_meal(conn: psycopg.Connection) -> None:
    plan_id = _two_day_plan(conn)
    plan = get_meal_plan(conn, plan_id)
    meal_id = plan["days"][0]["meals"][0]["meal_id"]

    delete_meal(conn, meal_id)

    # get_meal_plan inner-joins meals, so a day with no remaining meals drops out
    # of the view entirely — only day two is left.
    plan = get_meal_plan(conn, plan_id)
    dates = [d["date"] for d in plan["days"]]
    assert dates == [date(2026, 6, 11)]
