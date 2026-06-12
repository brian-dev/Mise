"""Persistence + ingredient canonicalization (AI_LAYER §5, §7).

The AI service writes generated plans with a privileged Postgres connection
(ARCHITECTURE §6) and does its own authorization in the calling layer. All
writes for one plan happen in a single transaction so a partial plan never
lands, and ingredient inserts are idempotent against the `ingredients.name`
unique constraint.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .config import settings
from .schemas import GeneratedMealPlan, GeneratedRecipe, MealPlanRequest


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


# --------------------------------------------------------------------------- #
# Read/helper queries for the local web harness (dev convenience, not the final
# client data path — ARCHITECTURE §9 has clients read Supabase directly).
# --------------------------------------------------------------------------- #
def create_household(
    conn: psycopg.Connection, name: str, owner_user_id: UUID | None = None
) -> dict[str, Any]:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("insert into households (name) values (%s) returning id, name", (name,))
        hid, hname = cur.fetchone()  # type: ignore[misc]
        if owner_user_id is not None:
            cur.execute(
                "insert into household_members (household_id, user_id, role) "
                "values (%s, %s, 'owner')",
                (hid, owner_user_id),
            )
    return {"id": hid, "name": hname}


def list_households(
    conn: psycopg.Connection, user_id: UUID | None = None
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        if user_id is None:
            # Anonymous dev mode (auth disabled): list all households.
            cur.execute("select id, name from households order by created_at desc")
        else:
            cur.execute(
                """
                select h.id, h.name from households h
                join household_members m on m.household_id = h.id
                where m.user_id = %s
                order by h.created_at desc
                """,
                (user_id,),
            )
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


# --- household resolvers (for membership checks on parent-scoped resources) -- #
def household_for_meal_plan(conn: psycopg.Connection, meal_plan_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute("select household_id from meal_plans where id = %s", (meal_plan_id,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"meal_plan {meal_plan_id} not found")
    return cast(UUID, row[0])


def household_for_shopping_list(conn: psycopg.Connection, shopping_list_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "select mp.household_id from shopping_lists sl "
            "join meal_plans mp on mp.id = sl.meal_plan_id where sl.id = %s",
            (shopping_list_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"shopping_list {shopping_list_id} not found")
    return cast(UUID, row[0])


def household_for_meal(conn: psycopg.Connection, meal_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "select mp.household_id from meals m "
            "join meal_plan_days d on d.id = m.meal_plan_day_id "
            "join meal_plans mp on mp.id = d.meal_plan_id where m.id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"meal {meal_id} not found")
    return cast(UUID, row[0])


def latest_meal_plan_id(conn: psycopg.Connection, household_id: UUID) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute(
            "select id from meal_plans where household_id = %s order by created_at desc limit 1",
            (household_id,),
        )
        row = cur.fetchone()
    return cast(UUID, row[0]) if row is not None else None


def meal_swap_context(conn: psycopg.Connection, meal_id: UUID) -> dict[str, Any]:
    """Gather what a recipe swap needs: meal type/servings, the household, and the
    other recipe titles in the same plan (for variety)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select m.meal_type, m.servings, mp.household_id, mp.id, m.recipe_id
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join meal_plans mp on mp.id = d.meal_plan_id
            where m.id = %s
            """,
            (meal_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"meal {meal_id} not found")
        meal_type, servings, household_id, meal_plan_id, recipe_id = row

        cur.execute(
            """
            select distinct r.title
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s and m.id <> %s
            """,
            (meal_plan_id, meal_id),
        )
        avoid_titles = [r[0] for r in cur.fetchall()]
    return {
        "meal_type": meal_type,
        "servings": servings,
        "household_id": household_id,
        "avoid_titles": avoid_titles,
        "recipe_id": recipe_id,
    }


def get_recipe_for_prompt(conn: psycopg.Connection, recipe_id: UUID) -> dict[str, Any]:
    """Reconstruct a recipe as the AI emits it (ingredient names, not ids) so it can
    be passed back as the base for iteration (AI_LAYER §8)."""
    with conn.cursor() as cur:
        cur.execute(
            "select title, description, cuisine_tags, prep_time, cook_time, "
            "default_servings, instructions from recipes where id = %s",
            (recipe_id,),
        )
        r = cur.fetchone()
        if r is None:
            raise ValueError(f"recipe {recipe_id} not found")
        cur.execute(
            """
            select i.name, ri.quantity, ri.unit, ri.is_optional
            from recipe_ingredients ri join ingredients i on i.id = ri.ingredient_id
            where ri.recipe_id = %s
            """,
            (recipe_id,),
        )
        ingredients = [
            {
                "name": row[0],
                "quantity": float(row[1]),
                "unit": row[2],
                "is_optional": row[3],
            }
            for row in cur.fetchall()
        ]
    return {
        "title": r[0],
        "description": r[1],
        "cuisine_tags": r[2],
        "prep_time": r[3],
        "cook_time": r[4],
        "default_servings": r[5],
        "instructions": r[6],
        "ingredients": ingredients,
    }


def get_recipe_detail(conn: psycopg.Connection, recipe_id: UUID) -> dict[str, Any]:
    """Full recipe for the UI: header, instructions, image, and ingredients
    (name + quantity + unit). Distinct from `get_recipe_for_prompt`, which shapes
    the recipe for re-prompting."""
    with conn.cursor() as cur:
        cur.execute(
            "select title, description, cuisine_tags, prep_time, cook_time, "
            "default_servings, instructions, image_url from recipes where id = %s",
            (recipe_id,),
        )
        r = cur.fetchone()
        if r is None:
            raise ValueError(f"recipe {recipe_id} not found")
        cur.execute(
            """
            select i.name, ri.quantity, ri.unit, ri.is_optional
            from recipe_ingredients ri join ingredients i on i.id = ri.ingredient_id
            where ri.recipe_id = %s
            order by ri.is_optional, i.name
            """,
            (recipe_id,),
        )
        ingredients = [
            {"name": row[0], "quantity": row[1], "unit": row[2], "is_optional": row[3]}
            for row in cur.fetchall()
        ]
    return {
        "recipe_id": recipe_id,
        "title": r[0],
        "description": r[1],
        "cuisine_tags": r[2],
        "prep_time": r[3],
        "cook_time": r[4],
        "default_servings": r[5],
        "instructions": r[6],
        "image_url": r[7],
        "ingredients": ingredients,
    }


def set_recipe_image(conn: psycopg.Connection, recipe_id: UUID, image_url: str) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "update recipes set image_url = %s where id = %s", (image_url, recipe_id)
        )


def swap_meal_recipe(
    conn: psycopg.Connection, meal_id: UUID, recipe: GeneratedRecipe
) -> UUID:
    """Persist a new recipe (shared pool, canonicalized ingredients) and point the
    meal at it. Returns the new recipe id."""
    with conn.transaction(), conn.cursor() as cur:
        recipe_id = _persist_recipe(cur, recipe)
        cur.execute("update meals set recipe_id = %s where id = %s", (recipe_id, meal_id))
    return recipe_id


def add_to_pantry(
    conn: psycopg.Connection,
    household_id: UUID,
    ingredient_name: str,
    quantity: Decimal,
    unit: str,
) -> dict[str, Any]:
    """Canonicalize the ingredient and add the quantity to the household pantry
    (upsert by ingredient+unit). Returns the resolved ingredient."""
    with conn.transaction(), conn.cursor() as cur:
        ingredient_id = canonicalize_ingredient(cur, ingredient_name, None)
        cur.execute(
            """
            insert into pantry_items (household_id, ingredient_id, quantity, unit)
            values (%s, %s, %s, %s)
            on conflict (household_id, ingredient_id, unit)
            do update set quantity = pantry_items.quantity + excluded.quantity
            """,
            (household_id, ingredient_id, quantity, unit),
        )
        cur.execute("select name from ingredients where id = %s", (ingredient_id,))
        name: str = cur.fetchone()[0]  # type: ignore[index]
    return {"ingredient_id": ingredient_id, "name": name}


def get_pantry(conn: psycopg.Connection, household_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select i.name, p.quantity, p.unit
            from pantry_items p join ingredients i on i.id = p.ingredient_id
            where p.household_id = %s
            order by i.name
            """,
            (household_id,),
        )
        return [{"name": r[0], "quantity": r[1], "unit": r[2]} for r in cur.fetchall()]


def get_meal_plan(conn: psycopg.Connection, meal_plan_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "select status, start_date, end_date, budget from meal_plans where id = %s",
            (meal_plan_id,),
        )
        head = cur.fetchone()
        if head is None:
            raise ValueError(f"meal_plan {meal_plan_id} not found")

        cur.execute(
            """
            select d.date, m.id, m.meal_type, m.servings, m.cooked_at, r.id, r.title
            from meal_plan_days d
            join meals m on m.meal_plan_day_id = d.id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s
            order by d.date, m.meal_type
            """,
            (meal_plan_id,),
        )
        days: dict[Any, list[dict[str, Any]]] = {}
        for date_, meal_id, meal_type, servings, cooked_at, recipe_id, title in cur.fetchall():
            days.setdefault(date_, []).append(
                {
                    "meal_id": meal_id,
                    "meal_type": meal_type,
                    "servings": servings,
                    "cooked_at": cooked_at,
                    "recipe_id": recipe_id,
                    "recipe_title": title,
                }
            )
    return {
        "meal_plan_id": meal_plan_id,
        "status": head[0],
        "start_date": head[1],
        "end_date": head[2],
        "budget": head[3],
        "days": [{"date": d, "meals": meals} for d, meals in sorted(days.items())],
    }


def create_generation_job(
    conn: psycopg.Connection,
    household_id: UUID,
    kind: str,
    request: dict[str, Any],
    requested_by: UUID | None = None,
) -> UUID:
    """Create a queued generation job (ARCHITECTURE §5)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            insert into generation_jobs (household_id, requested_by, kind, status, request)
            values (%s, %s, %s, 'queued', %s)
            returning id
            """,
            (household_id, requested_by, kind, Jsonb(request)),
        )
        return cast(UUID, cur.fetchone()[0])  # type: ignore[index]


def set_job_status(
    conn: psycopg.Connection,
    job_id: UUID,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "update generation_jobs set status = %s, result = %s, error = %s where id = %s",
            (status, Jsonb(result) if result is not None else None, error, job_id),
        )


def get_job(conn: psycopg.Connection, job_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "select id, kind, status, result, error, created_at, updated_at "
            "from generation_jobs where id = %s",
            (job_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"job {job_id} not found")
    return {
        "id": row[0],
        "kind": row[1],
        "status": row[2],
        "result": row[3],
        "error": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def get_shopping_list(conn: psycopg.Connection, shopping_list_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "select status, estimated_total from shopping_lists where id = %s",
            (shopping_list_id,),
        )
        head = cur.fetchone()
        if head is None:
            raise ValueError(f"shopping_list {shopping_list_id} not found")
        cur.execute(
            """
            select i.name, s.quantity_needed, s.unit, s.estimated_price, s.is_checked, s.source
            from shopping_list_items s join ingredients i on i.id = s.ingredient_id
            where s.shopping_list_id = %s
            order by i.name
            """,
            (shopping_list_id,),
        )
        items = [
            {
                "name": r[0],
                "quantity_needed": r[1],
                "unit": r[2],
                "estimated_price": r[3],
                "is_checked": r[4],
                "source": r[5],
            }
            for r in cur.fetchall()
        ]
    return {
        "shopping_list_id": shopping_list_id,
        "status": head[0],
        "estimated_total": head[1],
        "items": items,
    }


def get_user_theme(conn: psycopg.Connection, user_id: UUID) -> str | None:
    with conn.cursor() as cur:
        cur.execute("select theme from users where id = %s", (user_id,))
        row = cur.fetchone()
    return cast("str | None", row[0]) if row is not None else None


def set_user_theme(conn: psycopg.Connection, user_id: UUID, theme: str) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("update users set theme = %s where id = %s", (theme, user_id))


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
