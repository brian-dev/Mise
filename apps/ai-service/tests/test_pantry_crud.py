"""Pantry CRUD helpers — manual add, quantity update, delete, and the id/category
exposure that the editable pantry UI needs.

DB-marked; rolled-back transaction against the local stack.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from mise_ai.db import (
    add_to_pantry,
    delete_pantry_item,
    get_pantry,
    set_pantry_quantity,
)

pytestmark = pytest.mark.db


def _household(cur: psycopg.Cursor) -> UUID:
    cur.execute("insert into households (name) values ('Pantry HH') returning id")
    return cur.fetchone()[0]  # type: ignore[index]


def test_get_pantry_exposes_id_and_category(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)
    add_to_pantry(conn, hid, "Yellow Onion", Decimal("2"), "lb")
    item = get_pantry(conn, hid)[0]
    assert item["id"] is not None
    assert item["name"] == "Yellow Onion"
    assert item["category"] == "produce"
    assert item["quantity"] == Decimal("2.000")


def test_manual_add_upserts_by_ingredient_unit(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)
    add_to_pantry(conn, hid, "Yellow Onion", Decimal("2"), "lb")
    add_to_pantry(conn, hid, "yellow onion", Decimal("1.5"), "lb")  # same item+unit
    pantry = get_pantry(conn, hid)
    assert len(pantry) == 1
    assert pantry[0]["quantity"] == Decimal("3.500")


def test_set_quantity_and_delete(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        hid = _household(cur)
    add_to_pantry(conn, hid, "Garlic", Decimal("1"), "unit")
    item_id = get_pantry(conn, hid)[0]["id"]

    set_pantry_quantity(conn, hid, item_id, Decimal("5"))
    assert get_pantry(conn, hid)[0]["quantity"] == Decimal("5.000")

    delete_pantry_item(conn, hid, item_id)
    assert get_pantry(conn, hid) == []


def test_mutations_scoped_to_household(conn: psycopg.Connection) -> None:
    # An item_id from one household can't be mutated via another household's id.
    with conn.cursor() as cur:
        hid_a = _household(cur)
        cur.execute("insert into households (name) values ('Other HH') returning id")
        hid_b = cur.fetchone()[0]  # type: ignore[index]
    add_to_pantry(conn, hid_a, "Garlic", Decimal("1"), "unit")
    item_id = get_pantry(conn, hid_a)[0]["id"]

    delete_pantry_item(conn, hid_b, item_id)  # wrong household -> no-op
    assert len(get_pantry(conn, hid_a)) == 1
