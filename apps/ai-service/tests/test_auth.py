"""Auth tests: JWT verification (offline) + household-membership authorization
(against the live local Postgres, rolled back)."""

from __future__ import annotations

import time
import uuid
from uuid import UUID

import jwt
import psycopg
import pytest
from fastapi import HTTPException

from mise_ai.auth import _decode, current_user, is_member, require_membership
from mise_ai.config import settings
from mise_ai.db import create_household


def _token(sub: str, *, aud: str = "authenticated", exp_offset: int = 3600,
           secret: str | None = None) -> str:
    return jwt.encode(
        {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_offset},
        secret or settings.supabase_jwt_secret,
        algorithm="HS256",
    )


# ---- JWT verification (offline) ------------------------------------------- #
def test_valid_token_yields_user_id() -> None:
    uid = str(uuid.uuid4())
    assert _decode(_token(uid)) == UUID(uid)


def test_wrong_secret_rejected() -> None:
    with pytest.raises(HTTPException) as ei:
        _decode(_token(str(uuid.uuid4()), secret="not-the-real-secret-not-the-real-secret"))
    assert ei.value.status_code == 401


def test_wrong_audience_rejected() -> None:
    with pytest.raises(HTTPException) as ei:
        _decode(_token(str(uuid.uuid4()), aud="anon"))
    assert ei.value.status_code == 401


def test_expired_token_rejected() -> None:
    with pytest.raises(HTTPException) as ei:
        _decode(_token(str(uuid.uuid4()), exp_offset=-10))
    assert ei.value.status_code == 401


def test_current_user_requires_token_when_enforced() -> None:
    # require_auth defaults to True -> a missing token is rejected with 401.
    assert settings.require_auth is True
    with pytest.raises(HTTPException) as ei:
        current_user(authorization=None)
    assert ei.value.status_code == 401


def test_current_user_decodes_bearer() -> None:
    uid = str(uuid.uuid4())
    assert current_user(authorization=f"Bearer {_token(uid)}") == UUID(uid)


# ---- Membership authorization (live Postgres; `conn` fixture from conftest) -- #
def _make_user(cur: psycopg.Cursor, email: str) -> UUID:
    """Insert an auth.users row; the 0003 trigger mirrors it into public.users."""
    uid = uuid.uuid4()
    cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, email))
    return uid


@pytest.mark.db
def test_membership_isolation(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        alice = _make_user(cur, f"alice-{uuid.uuid4()}@test.dev")
        bob = _make_user(cur, f"bob-{uuid.uuid4()}@test.dev")

    # Alice creates a household (becomes owner member); Bob is unrelated.
    hh = create_household(conn, "Alice HH", owner_user_id=alice)
    household_id = hh["id"]

    with conn.cursor() as cur:
        assert is_member(cur.connection, alice, household_id) is True
        assert is_member(cur.connection, bob, household_id) is False

    # Owner passes; non-member is rejected 403; anonymous (None) is a no-op.
    require_membership(conn, alice, household_id)  # no raise
    require_membership(conn, None, household_id)  # no raise (auth disabled path)
    with pytest.raises(HTTPException) as ei:
        require_membership(conn, bob, household_id)
    assert ei.value.status_code == 403
