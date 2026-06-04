"""Seed a demo household + meal plan so you can exercise the shopping-list and
cook endpoints without calling Claude.

Usage (from apps/ai-service, with the local Supabase stack running):
    uv run python scripts/seed_demo.py

Prints the created meal_plan_id and a meal_id, plus ready-to-run curl commands.
Writes real rows to the local DB (it's your dev database).
"""

from __future__ import annotations

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


def main() -> None:
    conn = connect()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into households (name) values ('Demo Household') returning id"
            )
            household_id = cur.fetchone()[0]  # type: ignore[index]
            cur.execute("select id from ingredients where name = 'Yellow Onion'")
            onion_id = cur.fetchone()[0]  # type: ignore[index]
            # Stock some onion so pantry subtraction + depletion are visible.
            cur.execute(
                "insert into pantry_items (household_id, ingredient_id, quantity, unit) "
                "values (%s, %s, 1.0, 'lb')",
                (household_id, onion_id),
            )

        req = MealPlanRequest(
            household_id=household_id,
            start_date="2026-06-10",  # type: ignore[arg-type]
            end_date="2026-06-11",  # type: ignore[arg-type]
            household_size=4,
            meal_types=[MealType.dinner],
            budget=15.00,
        )
        recipe = GeneratedRecipe(
            title="Onion & Rice Skillet",
            cuisine_tags=["american"],
            default_servings=4,
            instructions="Saute onion, add rice and stock, simmer 20 min.",
            ingredients=[
                GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.lb),
                GeneratedIngredient(name="rice", quantity=1, unit=Unit.lb),
            ],
        )
        plan = GeneratedMealPlan(
            days=[
                GeneratedDay(
                    date=d,  # type: ignore[arg-type]
                    meals=[GeneratedMeal(meal_type=MealType.dinner, servings=4, recipe=recipe)],
                )
                for d in ("2026-06-10", "2026-06-11")
            ]
        )
        meal_plan_id = persist_meal_plan(conn, plan, req)

        with conn.cursor() as cur:
            cur.execute(
                """
                select m.id from meals m
                join meal_plan_days d on d.id = m.meal_plan_day_id
                where d.meal_plan_id = %s
                order by d.date
                limit 1
                """,
                (meal_plan_id,),
            )
            meal_id = cur.fetchone()[0]  # type: ignore[index]

        conn.commit()
    finally:
        conn.close()

    print(f"household_id : {household_id}")
    print(f"meal_plan_id : {meal_plan_id}")
    print(f"meal_id      : {meal_id}")
    print("\nTry the endpoints (server on :8000):\n")
    print("  curl -s -X POST localhost:8000/v1/shopping-lists/build \\")
    print("    -H 'content-type: application/json' \\")
    print(f"    -d '{{\"meal_plan_id\": \"{meal_plan_id}\"}}'\n")
    print(f"  curl -s -X POST localhost:8000/v1/meals/{meal_id}/cook \\")
    print("    -H 'content-type: application/json' -d '{}'")


if __name__ == "__main__":
    main()
