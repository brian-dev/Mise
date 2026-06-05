"""Shared pytest fixtures.

`conn` is the canonical self-cleaning database fixture (see CLAUDE.md → Testing):
it opens a connection against the local Supabase stack, runs the test inside a
transaction, and **rolls back** in teardown so no test rows are ever committed.
DB-touching tests take this fixture and carry the `db` marker; they skip cleanly
when Postgres isn't reachable.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from mise_ai.db import connect


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    try:
        c = connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local Postgres not reachable: {e}")
    c.autocommit = False
    try:
        yield c
    finally:
        c.rollback()  # discard everything this test wrote — keep the dev DB clean
        c.close()
