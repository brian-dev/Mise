"""Persistence + ingredient canonicalization (AI_LAYER §5, §7).

The AI service writes generated plans with a privileged Postgres connection
(ARCHITECTURE §6) and does its own authorization in the calling layer. All
writes for one plan happen in a single transaction so a partial plan never
lands, and ingredient inserts are idempotent against the `ingredients.name`
unique constraint.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import psycopg

from .config import settings
from .schemas import GeneratedMealPlan, GeneratedRecipe, MealPlanRequest


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


def normalize_name(name: str) -> str:
    """Lowercase + collapse whitespace. Canonical names live in the catalog;
    the emitted name is only used to find/create the catalog row (AI_LAYER §5)."""
    return " ".join(name.lower().split())


def canonicalize_ingredient(
    cur: psycopg.Cursor, name: str, category: str | None
) -> UUID:
    """Resolve an emitted ingredient name to an `ingredients.id`.

    Exact (case-insensitive) match → fuzzy pg_trgm match ≥ threshold → else
    insert a new catalog row (null USDA price until the next sync, AI_LAYER §5).
    """
    norm = normalize_name(name)

    # 1. Exact, case-insensitive.
    cur.execute("select id from ingredients where lower(name) = %s", (norm,))
    row = cur.fetchone()
    if row is not None:
        return cast(UUID, row[0])

    # 2. Fuzzy via the pg_trgm GIN index (`%` operator), threshold applied here.
    cur.execute(
        """
        select id, similarity(name, %s) as sim
        from ingredients
        where name %% %s
        order by sim desc
        limit 1
        """,
        (norm, norm),
    )
    row = cur.fetchone()
    if row is not None and row[1] >= settings.ingredient_match_threshold:
        return cast(UUID, row[0])

    # 3. Insert new. ON CONFLICT handles a concurrent insert of the same name.
    cur.execute(
        """
        insert into ingredients (name, category) values (%s, %s)
        on conflict (name) do nothing
        returning id
        """,
        (norm, category),
    )
    row = cur.fetchone()
    if row is not None:
        return cast(UUID, row[0])
    # Lost the race — the row now exists; fetch it.
    cur.execute("select id from ingredients where name = %s", (norm,))
    return cast(UUID, cur.fetchone()[0])  # type: ignore[index]


def _persist_recipe(cur: psycopg.Cursor, recipe: GeneratedRecipe) -> UUID:
    cur.execute(
        """
        insert into recipes
          (created_by_user_id, title, description, cuisine_tags, prep_time,
           cook_time, default_servings, instructions, is_ai_generated, source_prompt)
        values (null, %s, %s, %s, %s, %s, %s, %s, true, null)
        returning id
        """,
        (
            recipe.title,
            recipe.description,
            recipe.cuisine_tags,
            recipe.prep_time,
            recipe.cook_time,
            recipe.default_servings,
            recipe.instructions,
        ),
    )
    recipe_id: UUID = cur.fetchone()[0]  # type: ignore[index]

    for ing in recipe.ingredients:
        ingredient_id = canonicalize_ingredient(cur, ing.name, ing.category)
        cur.execute(
            """
            insert into recipe_ingredients
              (recipe_id, ingredient_id, quantity, unit, is_optional)
            values (%s, %s, %s, %s, %s)
            """,
            (recipe_id, ingredient_id, ing.quantity, ing.unit.value, ing.is_optional),
        )
    return recipe_id


def persist_meal_plan(
    conn: psycopg.Connection, plan: GeneratedMealPlan, req: MealPlanRequest
) -> UUID:
    """Persist a validated plan as a draft. Returns the new meal_plan id.

    Recipes are de-duplicated within the plan by title (AI_LAYER §7): an
    identical recipe emitted on two days is inserted once and shared.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            insert into meal_plans (household_id, status, start_date, end_date, budget)
            values (%s, 'draft', %s, %s, %s)
            returning id
            """,
            (req.household_id, req.start_date, req.end_date, req.budget),
        )
        meal_plan_id: UUID = cur.fetchone()[0]  # type: ignore[index]

        recipe_ids: dict[str, UUID] = {}
        for day in plan.days:
            cur.execute(
                """
                insert into meal_plan_days (meal_plan_id, date) values (%s, %s)
                returning id
                """,
                (meal_plan_id, day.date),
            )
            day_id: UUID = cur.fetchone()[0]  # type: ignore[index]

            for meal in day.meals:
                key = meal.recipe.title.strip().lower()
                recipe_id = recipe_ids.get(key)
                if recipe_id is None:
                    recipe_id = _persist_recipe(cur, meal.recipe)
                    recipe_ids[key] = recipe_id
                cur.execute(
                    """
                    insert into meals (meal_plan_day_id, meal_type, recipe_id, servings)
                    values (%s, %s, %s, %s)
                    """,
                    (
                        day_id,
                        meal.meal_type.value,
                        recipe_id,
                        meal.servings or req.household_size,
                    ),
                )

    return meal_plan_id
