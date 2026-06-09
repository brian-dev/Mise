"""Recipe swap: meal_swap_context + swap_meal_recipe (live Postgres, rolled back),
plus an opt-in live test for generate_recipe (real Claude)."""

from __future__ import annotations

import psycopg
import pytest

from mise_ai.db import (
    create_household,
    meal_swap_context,
    persist_meal_plan,
    swap_meal_recipe,
)
from mise_ai.generation import generate_recipe
from mise_ai.schemas import (
    Dietary,
    GeneratedDay,
    GeneratedIngredient,
    GeneratedMeal,
    GeneratedMealPlan,
    GeneratedRecipe,
    MealPlanRequest,
    MealType,
    RecipeRequest,
    Unit,
)


def _recipe(title: str) -> GeneratedRecipe:
    return GeneratedRecipe(
        title=title,
        cuisine_tags=["american"],
        default_servings=2,
        instructions="cook",
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=1, unit=Unit.lb)],
    )


@pytest.mark.db
def test_swap_context_and_replace(conn: psycopg.Connection) -> None:
    household_id = create_household(conn, "HH")["id"]
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
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner, servings=2, recipe=_recipe("Chili")
                    )
                ],
            ),
            GeneratedDay(
                date="2026-06-11",  # type: ignore[arg-type]
                meals=[
                    GeneratedMeal(
                        meal_type=MealType.dinner, servings=2, recipe=_recipe("Tacos")
                    )
                ],
            ),
        ]
    )
    meal_plan_id = persist_meal_plan(conn, plan, req)
    with conn.cursor() as cur:
        cur.execute(
            "select m.id, m.recipe_id from meals m "
            "join meal_plan_days d on d.id = m.meal_plan_day_id "
            "join recipes r on r.id = m.recipe_id "
            "where d.meal_plan_id = %s and r.title = 'Chili'",
            (meal_plan_id,),
        )
        meal_id, old_recipe_id = cur.fetchone()  # type: ignore[misc]

    # Context: the OTHER meal's title is offered as something to avoid.
    ctx = meal_swap_context(conn, meal_id)
    assert ctx["household_id"] == household_id
    assert str(ctx["meal_type"]) == "dinner"
    assert ctx["servings"] == 2
    assert ctx["avoid_titles"] == ["Tacos"]

    # Swap points the meal at a brand-new recipe.
    new_recipe_id = swap_meal_recipe(conn, meal_id, _recipe("Stir Fry"))
    assert new_recipe_id != old_recipe_id
    with conn.cursor() as cur:
        cur.execute("select recipe_id from meals where id = %s", (meal_id,))
        assert cur.fetchone()[0] == new_recipe_id  # type: ignore[index]
        cur.execute("select title from recipes where id = %s", (new_recipe_id,))
        assert cur.fetchone()[0] == "Stir Fry"  # type: ignore[index]


@pytest.mark.live
def test_live_generate_recipe() -> None:
    req = RecipeRequest(
        meal_type=MealType.dinner,
        servings=2,
        dietary=Dietary(flags=["vegetarian"], avoid_text="no mushrooms"),
        avoid_titles=["Lentil Curry", "Margherita Pizza"],
        modify="something quick and high-protein",
    )
    result = generate_recipe(req)
    assert result.recipe.title
    assert result.recipe.ingredients
    assert result.usage and result.usage[0].output_tokens > 0
