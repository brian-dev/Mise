"""Onboarding profile, consent ledger, and analytics events (db helpers).

DB-marked tests run against the local stack inside a rolled-back transaction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mise_ai.auth import current_user
from mise_ai.db import (
    get_current_consents,
    get_household_profile,
    log_event,
    record_consent,
    update_household_profile,
)
from mise_ai.main import app


def _household(cur: psycopg.Cursor) -> UUID:
    cur.execute("insert into households (name) values ('Profile HH') returning id")
    return cur.fetchone()[0]  # type: ignore[index]


def _user(cur: psycopg.Cursor) -> UUID:
    uid = uuid.uuid4()
    cur.execute(
        "insert into auth.users (id, email) values (%s, %s)",
        (uid, f"onb-{uid}@mise.test"),
    )
    return uid


@pytest.mark.db
def test_profile_defaults_then_updates(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)

    p = get_household_profile(conn, hid)
    assert p["household_size"] is None
    assert p["preferred_cuisines"] == []
    assert p["onboarding_completed_at"] is None

    update_household_profile(
        conn,
        hid,
        {
            "household_size": 4,
            "weekly_budget": Decimal("75.00"),
            "preferred_cuisines": ["Italian", "Thai"],
            "preferred_meal_types": ["dinner"],
            "cooking_time": "quick",
            "region": "NC",
        },
        complete_onboarding=True,
    )

    p = get_household_profile(conn, hid)
    assert p["household_size"] == 4
    assert p["weekly_budget"] == Decimal("75.00")
    assert p["preferred_cuisines"] == ["Italian", "Thai"]
    assert p["cooking_time"] == "quick"
    assert p["region"] == "NC"
    assert p["onboarding_completed_at"] is not None


@pytest.mark.db
def test_profile_update_ignores_unknown_fields(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)
    # 'name' / arbitrary keys are not in the whitelist and must be ignored.
    update_household_profile(conn, hid, {"name": "hacked", "household_size": 2})
    p = get_household_profile(conn, hid)
    assert p["name"] == "Profile HH"
    assert p["household_size"] == 2


@pytest.mark.db
def test_consent_ledger_latest_wins(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        uid = _user(cur)

    assert get_current_consents(conn, uid) == {}
    record_consent(conn, uid, "analytics", True, "2026-06-12")
    record_consent(conn, uid, "data_sharing", False, "2026-06-12")
    # Revoke analytics later -> latest row wins.
    record_consent(conn, uid, "analytics", False, "2026-06-12")

    current = get_current_consents(conn, uid)
    assert current == {"analytics": False, "data_sharing": False}

    # History is preserved (append-only): three rows total.
    with conn.cursor() as cur:
        cur.execute("select count(*) from user_consents where user_id = %s", (uid,))
        assert cur.fetchone()[0] == 3


@pytest.mark.db
def test_log_event_persists_properties(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)
    log_event(
        conn,
        "plan_generated",
        household_id=hid,
        properties={"days": 5, "cuisines": ["Italian"]},
    )
    with conn.cursor() as cur:
        cur.execute(
            "select event_type, properties from analytics_events where household_id = %s",
            (hid,),
        )
        row = cur.fetchone()
    assert row[0] == "plan_generated"  # type: ignore[index]
    assert row[1]["days"] == 5  # type: ignore[index]


# ---- Endpoint validation (no DB) -------------------------------------------- #
def test_post_consents_rejects_unknown_kind() -> None:
    app.dependency_overrides[current_user] = lambda: uuid.uuid4()
    try:
        res = TestClient(app).post(
            "/v1/me/consents",
            json={"version": "2026-06-12", "decisions": [{"kind": "wat", "granted": True}]},
        )
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert res.status_code == 422


def test_post_consents_requires_auth() -> None:
    app.dependency_overrides[current_user] = lambda: None
    try:
        res = TestClient(app).post(
            "/v1/me/consents",
            json={"version": "2026-06-12", "decisions": []},
        )
    finally:
        app.dependency_overrides.pop(current_user, None)
    assert res.status_code == 401
