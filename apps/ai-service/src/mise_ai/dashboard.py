"""Home-dashboard aggregation (UX_DESIGN.md — Dashboard is the app home).

Builds a single read model for the household home screen: the current plan's
state, the next few meals to cook, and ingredient alerts. All read-only; the
caller (main.py) does the membership check.

Ingredient alerts are three buckets:
  * use_soon          — pantry items whose estimated expiry (added_at + the
                        category shelf life from `category_shelf_life`, or a
                        per-ingredient override, or a default) falls within the
                        configured window.
  * running_low       — pantry items at/below the low-quantity threshold.
  * needed_not_stocked — non-optional ingredients required by the plan's
                        upcoming (uncooked) meals that aren't in the pantry.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from .config import settings


def build_dashboard(conn: psycopg.Connection, household_id: UUID) -> dict[str, Any]:
    """Assemble the home dashboard read model for a household."""
    plan = _latest_plan_summary(conn, household_id)
    upcoming = _upcoming_meals(conn, plan["meal_plan_id"]) if plan else []
    alerts = {
        "use_soon": _use_soon(conn, household_id),
        "running_low": _running_low(conn, household_id),
        "needed_not_stocked": (
            _needed_not_stocked(conn, household_id, plan["meal_plan_id"]) if plan else []
        ),
    }
    return {
        "household_id": household_id,
        "plan": plan,
        "upcoming_meals": upcoming,
        "alerts": alerts,
    }


def _latest_plan_summary(
    conn: psycopg.Connection, household_id: UUID
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, status, start_date, end_date, budget
            from meal_plans
            where household_id = %s
            order by created_at desc
            limit 1
            """,
            (household_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        meal_plan_id, status, start_date, end_date, budget = row

        cur.execute(
            """
            select count(*), count(m.cooked_at)
            from meal_plan_days d
            join meals m on m.meal_plan_day_id = d.id
            where d.meal_plan_id = %s
            """,
            (meal_plan_id,),
        )
        total, cooked = cur.fetchone()  # type: ignore[misc]

    return {
        "meal_plan_id": meal_plan_id,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "budget": budget,
        "meals_total": total,
        "meals_cooked": cooked,
    }


def _upcoming_meals(
    conn: psycopg.Connection, meal_plan_id: UUID
) -> list[dict[str, Any]]:
    """The next uncooked meals from today forward, soonest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select d.date, m.id, m.meal_type, r.id, r.title, r.image_url
            from meal_plan_days d
            join meals m on m.meal_plan_day_id = d.id
            join recipes r on r.id = m.recipe_id
            where d.meal_plan_id = %s
              and m.cooked_at is null
              and d.date >= current_date
            order by d.date, m.meal_type
            limit %s
            """,
            (meal_plan_id, settings.upcoming_meals_limit),
        )
        return [
            {
                "date": r[0],
                "meal_id": r[1],
                "meal_type": r[2],
                "recipe_id": r[3],
                "recipe_title": r[4],
                "image_url": r[5],
            }
            for r in cur.fetchall()
        ]


def _use_soon(conn: psycopg.Connection, household_id: UUID) -> list[dict[str, Any]]:
    """Pantry items whose estimated expiry falls within the configured window.

    Shelf life resolves per item as: ingredient override → category default →
    global default. Expiry = added_at::date + shelf_life_days.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select i.name, p.quantity, p.unit,
                   (p.added_at::date
                     + coalesce(i.shelf_life_days, csl.days, %s)) as expires_on
            from pantry_items p
            join ingredients i on i.id = p.ingredient_id
            left join category_shelf_life csl on csl.category = i.category
            where p.household_id = %s
              and p.quantity > 0
              and (p.added_at::date
                     + coalesce(i.shelf_life_days, csl.days, %s))
                  <= current_date + %s
            order by expires_on
            """,
            (
                settings.default_shelf_life_days,
                household_id,
                settings.default_shelf_life_days,
                settings.use_soon_window_days,
            ),
        )
        return [
            {"name": r[0], "quantity": r[1], "unit": r[2], "expires_on": r[3]}
            for r in cur.fetchall()
        ]


def _running_low(conn: psycopg.Connection, household_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select i.name, p.quantity, p.unit
            from pantry_items p
            join ingredients i on i.id = p.ingredient_id
            where p.household_id = %s
              and p.quantity > 0
              and p.quantity <= %s
            order by p.quantity, i.name
            """,
            (household_id, settings.running_low_threshold),
        )
        return [{"name": r[0], "quantity": r[1], "unit": r[2]} for r in cur.fetchall()]


def _needed_not_stocked(
    conn: psycopg.Connection, household_id: UUID, meal_plan_id: UUID
) -> list[dict[str, Any]]:
    """Non-optional ingredients for upcoming uncooked meals that the pantry lacks."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct i.name, ri.unit
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join recipes r on r.id = m.recipe_id
            join recipe_ingredients ri on ri.recipe_id = r.id
            join ingredients i on i.id = ri.ingredient_id
            where d.meal_plan_id = %s
              and m.cooked_at is null
              and ri.is_optional = false
              and not exists (
                select 1 from pantry_items p
                where p.household_id = %s
                  and p.ingredient_id = ri.ingredient_id
                  and p.quantity > 0
              )
            order by i.name
            """,
            (meal_plan_id, household_id),
        )
        return [{"name": r[0], "unit": r[1]} for r in cur.fetchall()]
