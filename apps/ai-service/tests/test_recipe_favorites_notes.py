"""Per-user recipe favorites + notes (db helpers).

DB-marked; rolled-back transaction against the local stack.
"""

from __future__ import annotations

import uuid
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import (
    get_recipe_detail,
    set_recipe_favorite,
    set_recipe_note,
)

pytestmark = pytest.mark.db


def _user(cur: psycopg.Cursor) -> UUID:
    uid = uuid.uuid4()
    cur.execute(
        "insert into auth.users (id, email) values (%s, %s)",
        (uid, f"rec-{uid}@mise.test"),
    )
    return uid


def _recipe(cur: psycopg.Cursor, title: str = "Test Dish") -> UUID:
    cur.execute(
        "insert into recipes (title, default_servings, instructions) "
        "values (%s, 2, 'Cook.') returning id",
        (title,),
    )
    return cur.fetchone()[0]  # type: ignore[index]


def test_favorite_toggle(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        uid = _user(cur)
        rid = _recipe(cur)

    assert get_recipe_detail(conn, rid, user_id=uid)["is_favorite"] is False
    set_recipe_favorite(conn, uid, rid, True)
    assert get_recipe_detail(conn, rid, user_id=uid)["is_favorite"] is True
    # Idempotent re-favorite.
    set_recipe_favorite(conn, uid, rid, True)
    set_recipe_favorite(conn, uid, rid, False)
    assert get_recipe_detail(conn, rid, user_id=uid)["is_favorite"] is False


def test_note_upsert_and_clear(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        uid = _user(cur)
        rid = _recipe(cur)

    assert get_recipe_detail(conn, rid, user_id=uid)["note"] is None
    set_recipe_note(conn, uid, rid, "  double the garlic  ")
    assert get_recipe_detail(conn, rid, user_id=uid)["note"] == "double the garlic"
    set_recipe_note(conn, uid, rid, "use less salt")
    assert get_recipe_detail(conn, rid, user_id=uid)["note"] == "use less salt"
    # Blank clears it.
    set_recipe_note(conn, uid, rid, "   ")
    assert get_recipe_detail(conn, rid, user_id=uid)["note"] is None


def test_favorites_and_notes_are_per_user(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        a = _user(cur)
        b = _user(cur)
        rid = _recipe(cur)
    set_recipe_favorite(conn, a, rid, True)
    set_recipe_note(conn, a, rid, "A's note")

    detail_b = get_recipe_detail(conn, rid, user_id=b)
    assert detail_b["is_favorite"] is False
    assert detail_b["note"] is None


def test_no_user_means_no_personal_fields(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        rid = _recipe(cur)
    detail = get_recipe_detail(conn, rid)  # no user_id
    assert detail["is_favorite"] is False
    assert detail["note"] is None
