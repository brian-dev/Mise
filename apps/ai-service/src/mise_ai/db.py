"""Persistence + ingredient canonicalization (AI_LAYER §5, §7).

The AI service writes generated plans with a privileged Postgres connection
(ARCHITECTURE §6) and does its own authorization in the calling layer. All
writes for one plan happen in a single transaction so a partial plan never
lands, and ingredient inserts are idempotent against the `ingredients.name`
unique constraint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .config import settings
from .schemas import GeneratedDay, GeneratedMealPlan, GeneratedRecipe, MealPlanRequest


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


def recipes_missing_image_for_plan(
    conn: psycopg.Connection, meal_plan_id: UUID
) -> list[dict[str, Any]]:
    """Distinct recipes used by a plan that don't yet have an image, with the
    title + cuisine needed to resolve one."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct r.id, r.title, r.cuisine_tags
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s and r.image_url is null
            """,
            (meal_plan_id,),
        )
        return [{"id": r[0], "title": r[1], "cuisine_tags": r[2]} for r in cur.fetchall()]


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


def day_regen_context(
    conn: psycopg.Connection, meal_plan_id: UUID, day: date
) -> dict[str, Any]:
    """What a single-day regeneration needs: the day row, household, the meal types
    to refill (the slots already on that day), a representative servings, and the
    other days' recipe titles (to bias away from repeats)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select d.id, mp.household_id
            from meal_plan_days d join meal_plans mp on mp.id = d.meal_plan_id
            where d.meal_plan_id = %s and d.date = %s
            """,
            (meal_plan_id, day),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"day {day} not found in meal_plan {meal_plan_id}")
        day_id, household_id = row

        cur.execute(
            "select meal_type, servings from meals where meal_plan_day_id = %s "
            "order by meal_type",
            (day_id,),
        )
        rows = cur.fetchall()
        meal_types = [r[0] for r in rows]
        servings = max((r[1] for r in rows), default=2)

        cur.execute(
            """
            select distinct r.title
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s and d.id <> %s
            """,
            (meal_plan_id, day_id),
        )
        avoid_titles = [r[0] for r in cur.fetchall()]
    return {
        "day_id": day_id,
        "household_id": household_id,
        "meal_types": meal_types,
        "servings": servings,
        "avoid_titles": avoid_titles,
    }


def replace_day_meals(
    conn: psycopg.Connection, day_id: UUID, day: GeneratedDay, default_servings: int
) -> None:
    """Swap out all meals on a day for freshly generated ones (single transaction).
    Recipes are de-duplicated within the day by title, like persist_meal_plan."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("delete from meals where meal_plan_day_id = %s", (day_id,))
        recipe_ids: dict[str, UUID] = {}
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
                (day_id, meal.meal_type.value, recipe_id, meal.servings or default_servings),
            )


def delete_meal(conn: psycopg.Connection, meal_id: UUID) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("delete from meals where id = %s", (meal_id,))


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
            select p.id, i.name, i.category, p.quantity, p.unit
            from pantry_items p join ingredients i on i.id = p.ingredient_id
            where p.household_id = %s
            order by coalesce(i.category, 'zzz'), i.name
            """,
            (household_id,),
        )
        return [
            {"id": r[0], "name": r[1], "category": r[2], "quantity": r[3], "unit": r[4]}
            for r in cur.fetchall()
        ]


def set_pantry_quantity(
    conn: psycopg.Connection, household_id: UUID, item_id: UUID, quantity: Decimal
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "update pantry_items set quantity = %s where id = %s and household_id = %s",
            (quantity, item_id, household_id),
        )


def delete_pantry_item(
    conn: psycopg.Connection, household_id: UUID, item_id: UUID
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "delete from pantry_items where id = %s and household_id = %s",
            (item_id, household_id),
        )


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
            select d.date, m.id, m.meal_type, m.servings, m.cooked_at,
                   r.id, r.title, r.image_url
            from meal_plan_days d
            join meals m on m.meal_plan_day_id = d.id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s
            order by d.date, m.meal_type
            """,
            (meal_plan_id,),
        )
        days: dict[Any, list[dict[str, Any]]] = {}
        for date_, meal_id, meal_type, servings, cooked_at, recipe_id, title, image_url in (
            cur.fetchall()
        ):
            days.setdefault(date_, []).append(
                {
                    "meal_id": meal_id,
                    "meal_type": meal_type,
                    "servings": servings,
                    "cooked_at": cooked_at,
                    "recipe_id": recipe_id,
                    "recipe_title": title,
                    "image_url": image_url,
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
            select s.id, i.name, i.category, s.quantity_needed, s.unit,
                   s.estimated_price, s.is_checked, s.source
            from shopping_list_items s join ingredients i on i.id = s.ingredient_id
            where s.shopping_list_id = %s
            order by coalesce(i.category, 'zzz'), i.name
            """,
            (shopping_list_id,),
        )
        items = [
            {
                "id": r[0],
                "name": r[1],
                "category": r[2],
                "quantity_needed": r[3],
                "unit": r[4],
                "estimated_price": r[5],
                "is_checked": r[6],
                "source": r[7],
            }
            for r in cur.fetchall()
        ]
    return {
        "shopping_list_id": shopping_list_id,
        "status": head[0],
        "estimated_total": head[1],
        "items": items,
    }


def _recompute_list_total(cur: psycopg.Cursor, shopping_list_id: UUID) -> None:
    """Refresh the stored estimated_total from the current item prices."""
    cur.execute(
        """
        update shopping_lists set estimated_total = coalesce(
          (select sum(estimated_price) from shopping_list_items
           where shopping_list_id = %s), 0)
        where id = %s
        """,
        (shopping_list_id, shopping_list_id),
    )


def set_item_checked(
    conn: psycopg.Connection, shopping_list_id: UUID, item_id: UUID, is_checked: bool
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "update shopping_list_items set is_checked = %s "
            "where id = %s and shopping_list_id = %s",
            (is_checked, item_id, shopping_list_id),
        )


def update_item_quantity(
    conn: psycopg.Connection, shopping_list_id: UUID, item_id: UUID, quantity: Decimal
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "update shopping_list_items set quantity_needed = %s "
            "where id = %s and shopping_list_id = %s",
            (quantity, item_id, shopping_list_id),
        )


def add_manual_item(
    conn: psycopg.Connection,
    shopping_list_id: UUID,
    name: str,
    quantity: Decimal,
    unit: str,
) -> dict[str, Any]:
    """Add a user-typed item to the list (canonicalized ingredient, source=manual,
    no price). Returns the created item row for the UI."""
    with conn.transaction(), conn.cursor() as cur:
        ingredient_id = canonicalize_ingredient(cur, name, None)
        cur.execute(
            """
            insert into shopping_list_items
              (shopping_list_id, ingredient_id, quantity_needed, unit, source)
            values (%s, %s, %s, %s, 'manual')
            returning id
            """,
            (shopping_list_id, ingredient_id, quantity, unit),
        )
        item_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("select name, category from ingredients where id = %s", (ingredient_id,))
        iname, category = cur.fetchone()  # type: ignore[misc]
    return {
        "id": item_id,
        "name": iname,
        "category": category,
        "quantity_needed": quantity,
        "unit": unit,
        "estimated_price": None,
        "is_checked": False,
        "source": "manual",
    }


def delete_item(
    conn: psycopg.Connection, shopping_list_id: UUID, item_id: UUID
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "delete from shopping_list_items where id = %s and shopping_list_id = %s",
            (item_id, shopping_list_id),
        )
        _recompute_list_total(cur, shopping_list_id)


# --------------------------------------------------------------------------- #
# Household profile (onboarding snapshot), consent ledger, analytics events.
# --------------------------------------------------------------------------- #

# Columns a client may set on the household profile (whitelist guards the SET).
_PROFILE_FIELDS = (
    "household_size",
    "weekly_budget",
    "preferred_cuisines",
    "preferred_meal_types",
    "cooking_time",
    "dietary_flags",
    "avoid_text",
    "region",
    "store_preference",
)


def onboarding_status(conn: psycopg.Connection, user_id: UUID) -> dict[str, Any]:
    """Whether this user still needs onboarding, and which household to fill.

    Needs onboarding = the user owns no household that has completed it. The
    target is the most recent not-yet-completed household to reuse (so a half-
    finished run doesn't spawn duplicates), or None to create a fresh one.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select h.id, h.onboarding_completed_at
            from households h
            join household_members m on m.household_id = h.id
            where m.user_id = %s and m.role = 'owner'
            order by h.created_at desc
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    completed = any(r[1] is not None for r in rows)
    incomplete = next((r[0] for r in rows if r[1] is None), None)
    return {
        "needs_onboarding": not completed,
        "household_id": None if completed else incomplete,
    }


def get_household_profile(conn: psycopg.Connection, household_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select name, household_size, weekly_budget, preferred_cuisines,
                   preferred_meal_types, cooking_time, dietary_flags, avoid_text,
                   region, store_preference, onboarding_completed_at
            from households where id = %s
            """,
            (household_id,),
        )
        r = cur.fetchone()
    if r is None:
        raise ValueError(f"household {household_id} not found")
    return {
        "name": r[0],
        "household_size": r[1],
        "weekly_budget": r[2],
        "preferred_cuisines": r[3],
        "preferred_meal_types": r[4],
        "cooking_time": r[5],
        "dietary_flags": r[6],
        "avoid_text": r[7],
        "region": r[8],
        "store_preference": r[9],
        "onboarding_completed_at": r[10],
    }


def update_household_profile(
    conn: psycopg.Connection,
    household_id: UUID,
    fields: dict[str, Any],
    complete_onboarding: bool = False,
) -> None:
    """Update whitelisted profile columns. Unknown keys are ignored. When
    `complete_onboarding`, stamp onboarding_completed_at (idempotently)."""
    sets = [f"{k} = %s" for k in fields if k in _PROFILE_FIELDS]
    values: list[Any] = [v for k, v in fields.items() if k in _PROFILE_FIELDS]
    if complete_onboarding:
        sets.append("onboarding_completed_at = coalesce(onboarding_completed_at, now())")
    if not sets:
        return
    values.append(household_id)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            f"update households set {', '.join(sets)} where id = %s",  # noqa: S608 (cols whitelisted)
            values,
        )


def record_consent(
    conn: psycopg.Connection, user_id: UUID, kind: str, granted: bool, version: str
) -> None:
    """Append a consent decision to the ledger (history-preserving)."""
    with conn.transaction(), conn.cursor() as cur:
        # clock_timestamp() (not now()) so rows written in the same transaction
        # still order correctly — now() is fixed at transaction start.
        cur.execute(
            "insert into user_consents (user_id, kind, granted, version, created_at) "
            "values (%s, %s, %s, %s, clock_timestamp())",
            (user_id, kind, granted, version),
        )


def get_current_consents(conn: psycopg.Connection, user_id: UUID) -> dict[str, bool]:
    """Current consent state per kind (latest ledger row wins)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (kind) kind, granted
            from user_consents
            where user_id = %s
            order by kind, created_at desc
            """,
            (user_id,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def log_event(
    conn: psycopg.Connection,
    event_type: str,
    user_id: UUID | None = None,
    household_id: UUID | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Append a structured analytics event. Best-effort at the call site."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "insert into analytics_events (user_id, household_id, event_type, properties) "
            "values (%s, %s, %s, %s)",
            (user_id, household_id, event_type, Jsonb(properties or {})),
        )


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
