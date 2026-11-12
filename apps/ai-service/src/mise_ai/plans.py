"""Meal plan status lifecycle (spec §3.2): ``draft`` → ``active`` → ``closed``.

* A freshly generated plan is a **draft** — reviewable and editable.
* **Activating** a plan makes it the household's working plan. At most one plan is
  active per household (enforced by the ``meal_plans_one_active_per_household``
  partial unique index), so activating closes whichever plan was active before.
  Cooking a meal or building a shopping list from a draft activates it implicitly —
  either one means the household has committed to the plan.
* A plan **closes** when the user closes it, when another plan is activated, or
  automatically once its last day has passed (applied lazily on read). Closed plans
  are kept for history and are read-only: no cooking, swapping or plan edits.

Auto-close waits ``settings.plan_autoclose_grace_days`` (default 1) past the end
date. The database's ``current_date`` is UTC while plan dates are the household's
local calendar days, so without the grace a plan ending "today" would close at 6pm
in Texas; the grace also leaves room to mark last night's dinner cooked.

The household's **current** plan — what the Plan tab and dashboard show — is its
newest non-closed plan. A freshly generated draft therefore surfaces immediately
(offering to replace the active one) and closing the current plan leads back to the
empty "generate a plan" state.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import psycopg

from .config import settings


class PlanStateError(ValueError):
    """The requested transition or edit isn't allowed in the plan's current status
    (the API maps this to 409)."""


def close_expired_plans(conn: psycopg.Connection, household_id: UUID) -> int:
    """Auto-close the household's open plans whose last day is behind us."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            update meal_plans
            set status = 'closed', closed_at = now()
            where household_id = %s
              and status <> 'closed'
              and end_date < current_date - %s
            """,
            (household_id, settings.plan_autoclose_grace_days),
        )
        return cur.rowcount


def current_meal_plan_id(conn: psycopg.Connection, household_id: UUID) -> UUID | None:
    """The household's newest non-closed plan (after auto-closing expired ones)."""
    close_expired_plans(conn, household_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            select id from meal_plans
            where household_id = %s and status <> 'closed'
            order by created_at desc
            limit 1
            """,
            (household_id,),
        )
        row = cur.fetchone()
    return cast(UUID, row[0]) if row is not None else None


def plan_for_meal(conn: psycopg.Connection, meal_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "select d.meal_plan_id from meals m "
            "join meal_plan_days d on d.id = m.meal_plan_day_id where m.id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"meal {meal_id} not found")
    return cast(UUID, row[0])


def _head(cur: psycopg.Cursor[Any], meal_plan_id: UUID, *, lock: bool = False) -> tuple[Any, ...]:
    cur.execute(
        "select household_id, status, end_date < current_date - %s "
        "from meal_plans where id = %s" + (" for update" if lock else ""),
        (settings.plan_autoclose_grace_days, meal_plan_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"meal_plan {meal_plan_id} not found")
    return cast(tuple[Any, ...], row)


def ensure_open(conn: psycopg.Connection, meal_plan_id: UUID) -> str:
    """Raise PlanStateError if the plan is closed (closed plans are read-only).
    Returns the plan's status."""
    with conn.cursor() as cur:
        _, status, _ = _head(cur, meal_plan_id)
    if status == "closed":
        raise PlanStateError(f"meal_plan {meal_plan_id} is closed")
    return cast(str, status)


def activate_plan(conn: psycopg.Connection, meal_plan_id: UUID) -> UUID | None:
    """Make a draft the household's active plan, closing the previously active one.

    Idempotent for an already-active plan. Returns the id of the plan that was
    closed to make room, if any. Raises PlanStateError for a closed plan or a draft
    whose dates have already passed.
    """
    with conn.transaction(), conn.cursor() as cur:
        household_id, status, ended = _head(cur, meal_plan_id, lock=True)
        if status == "active":
            return None
        if status == "closed":
            raise PlanStateError(f"meal_plan {meal_plan_id} is closed")
        if ended:
            raise PlanStateError(f"meal_plan {meal_plan_id} has already ended")
        # Lock the household's plans so two concurrent activations serialize
        # instead of tripping the one-active unique index.
        cur.execute(
            "select id from meal_plans where household_id = %s for update", (household_id,)
        )
        cur.execute(
            """
            update meal_plans
            set status = 'closed', closed_at = now()
            where household_id = %s and status = 'active'
            returning id
            """,
            (household_id,),
        )
        prev = cur.fetchone()
        cur.execute("update meal_plans set status = 'active' where id = %s", (meal_plan_id,))
    return cast(UUID, prev[0]) if prev is not None else None


def ensure_active(conn: psycopg.Connection, meal_plan_id: UUID) -> None:
    """Committing actions (cook, build shopping list) run against the active plan:
    a draft is activated on the spot; a closed plan is rejected."""
    if ensure_open(conn, meal_plan_id) == "draft":
        activate_plan(conn, meal_plan_id)


def close_plan(conn: psycopg.Connection, meal_plan_id: UUID) -> None:
    """Close a draft or active plan. Raises PlanStateError if already closed."""
    with conn.transaction(), conn.cursor() as cur:
        _, status, _ = _head(cur, meal_plan_id, lock=True)
        if status == "closed":
            raise PlanStateError(f"meal_plan {meal_plan_id} is already closed")
        cur.execute(
            "update meal_plans set status = 'closed', closed_at = now() where id = %s",
            (meal_plan_id,),
        )
