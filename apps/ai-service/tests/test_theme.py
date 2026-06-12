"""Per-user theme persistence (db helpers) + endpoint validation."""

from __future__ import annotations

import uuid
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mise_ai.auth import current_user
from mise_ai.db import get_user_theme, set_user_theme
from mise_ai.main import app


def _make_user(cur: psycopg.Cursor) -> UUID:
    """Insert an auth.users row; the 0003 trigger mirrors it into public.users."""
    uid = uuid.uuid4()
    cur.execute(
        "insert into auth.users (id, email) values (%s, %s)",
        (uid, f"theme-{uid}@mise.test"),
    )
    return uid


@pytest.mark.db
def test_theme_defaults_null_then_persists(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        user_id = _make_user(cur)

    assert get_user_theme(conn, user_id) is None
    set_user_theme(conn, user_id, "dark")
    assert get_user_theme(conn, user_id) == "dark"
    set_user_theme(conn, user_id, "fresh")
    assert get_user_theme(conn, user_id) == "fresh"


def test_put_theme_rejects_unknown_value() -> None:
    # Stub a signed-in user so validation runs without touching auth/DB.
    app.dependency_overrides[current_user] = lambda: uuid.uuid4()
    try:
        res = TestClient(app).put("/v1/me/theme", json={"theme": "neon"})
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert res.status_code == 422


def test_put_theme_requires_auth() -> None:
    # current_user resolves to None (unauthenticated) -> 401 on a write.
    app.dependency_overrides[current_user] = lambda: None
    try:
        res = TestClient(app).put("/v1/me/theme", json={"theme": "dark"})
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert res.status_code == 401
