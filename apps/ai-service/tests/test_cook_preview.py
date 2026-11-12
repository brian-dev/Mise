"""Partial-use prompt at cook time (spec §3.4): cook-preview flags + overrides.

Live Postgres via the rolled-back `conn` fixture; HTTP tests route the app's
`connect()` onto the same connection so endpoint writes roll back too.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mise_ai import main
from mise_ai.auth import current_user
from mise_ai.db import create_household, persist_meal_plan
from mise_ai.pantry import _tidy, cook_preview
from mise_ai.schemas import (
    GeneratedDay,
    GeneratedIngredient,
    GeneratedMeal,
    GeneratedMealPlan,
    GeneratedRecipe,
    MealPlanRequest,
    MealType,
    Unit,
)

pytestmark = pytest.mark.db


def _setup(conn: psycopg.Connection, mode: str = "auto") -> tuple[UUID, UUID, UUID]:
    """Household + 1-meal plan + pantry. Returns (owner, household_id, meal_id).

    Recipe (default_servings 4, meal servings 2 -> factor 0.5):
      crushed tomatoes 1 can  -> 0.5 can, 2 cans on hand   -> partial
      yellow onion     2 lb   -> 1 lb,    0.25 lb on hand  -> short
      rice             2 lb   -> 1 lb,    5 lb on hand     -> fine
      garlic           4 clove-> 2 clove, none on hand     -> not deductible
    """
    owner = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (owner, f"{owner}@t"))
    hid = create_household(conn, "Cook Preview HH", owner_user_id=owner)["id"]
    with conn.cursor() as cur:
        cur.execute("update households set pantry_depletion_mode = %s where id = %s", (mode, hid))

    req = MealPlanRequest(
        household_id=hid,
        start_date=date.today(),
        end_date=date.today(),
        household_size=2,
        meal_types=[MealType.dinner],
    )
    recipe = GeneratedRecipe(
        title="Tomato Rice",
        cuisine_tags=["italian"],
        default_servings=4,
        instructions="Simmer.",
        ingredients=[
            GeneratedIngredient(name="crushed tomatoes", quantity=1, unit=Unit.can),
            GeneratedIngredient(name="yellow onion", quantity=2, unit=Unit.lb),
            GeneratedIngredient(name="rice", quantity=2, unit=Unit.lb),
            GeneratedIngredient(name="garlic", quantity=4, unit=Unit.clove),
        ],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date=date.today(),
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=recipe)],
            )
        ]
    )
    pid = persist_meal_plan(conn, plan, req)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into pantry_items (household_id, ingredient_id, quantity, unit)
            select %s, ri.ingredient_id, v.qty, ri.unit
            from recipe_ingredients ri
            join ingredients i on i.id = ri.ingredient_id
            join (values ('Crushed Tomatoes', 2.0), ('Yellow Onion', 0.25), ('Rice', 5.0))
              as v(name, qty) on lower(v.name) = lower(i.name)
            join meals m on m.recipe_id = ri.recipe_id
            join meal_plan_days d on d.id = m.meal_plan_day_id and d.meal_plan_id = %s
            """,
            (hid, pid),
        )
        cur.execute(
            "select m.id from meals m join meal_plan_days d on d.id = m.meal_plan_day_id "
            "where d.meal_plan_id = %s",
            (pid,),
        )
        meal_id = cur.fetchone()[0]  # type: ignore[index]
    return owner, hid, meal_id


def _by_name(items: list, name: str):  # type: ignore[no-untyped-def]
    return next(i for i in items if i.name.lower() == name)


def test_tidy_avoids_exponent_notation() -> None:
    assert str(_tidy(Decimal("100.000"))) == "100"
    assert str(_tidy(Decimal("0.5000"))) == "0.5"
    assert str(_tidy(Decimal("1.33333"))) == "1.333"


def test_preview_flags_partial_and_short(conn: psycopg.Connection) -> None:
    _, _, meal_id = _setup(conn)
    p = cook_preview(conn, meal_id)
    assert p.mode == "auto" and p.servings == 2 and not p.already_cooked

    tomatoes = _by_name(p.ingredients, "crushed tomatoes")
    assert (tomatoes.planned, tomatoes.reason) == (Decimal("0.5"), "partial")
    onion = _by_name(p.ingredients, "yellow onion")
    assert (onion.planned, onion.reason) == (Decimal("1"), "short")
    rice = _by_name(p.ingredients, "rice")
    assert (rice.planned, rice.reason) == (Decimal("1"), None)
    garlic = _by_name(p.ingredients, "garlic")
    assert garlic.on_hand is None and garlic.reason is None


def test_preview_manual_mode_flags_nothing(conn: psycopg.Connection) -> None:
    _, _, meal_id = _setup(conn, mode="manual")
    p = cook_preview(conn, meal_id)
    assert p.mode == "manual"
    assert all(i.reason is None for i in p.ingredients)


# ---- HTTP ------------------------------------------------------------------ #
@pytest.fixture
def client(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    @contextmanager
    def _shared() -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(main, "connect", _shared)
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(current_user, None)


def _pantry(conn: psycopg.Connection, hid: UUID, name: str) -> Decimal:
    with conn.cursor() as cur:
        cur.execute(
            "select p.quantity from pantry_items p join ingredients i on i.id = p.ingredient_id "
            "where p.household_id = %s and lower(i.name) = %s",
            (hid, name),
        )
        return cur.fetchone()[0]  # type: ignore[index,no-any-return]


def test_http_preview_then_cook_with_overrides(
    conn: psycopg.Connection, client: TestClient
) -> None:
    owner, hid, meal_id = _setup(conn)
    main.app.dependency_overrides[current_user] = lambda: owner

    res = client.get(f"/v1/meals/{meal_id}/cook-preview")
    assert res.status_code == 200
    body = res.json()
    assert body["needs_confirm"] is True
    flagged = {i["name"].lower(): i for i in body["ingredients"] if i["reason"]}
    assert set(flagged) == {"crushed tomatoes", "yellow onion"}
    assert flagged["crushed tomatoes"]["planned"] == "0.5"

    # The user says they used the whole can and the last of the onion.
    tomatoes = flagged["crushed tomatoes"]["ingredient_id"]
    onion = flagged["yellow onion"]["ingredient_id"]
    res = client.post(
        f"/v1/meals/{meal_id}/cook", json={"overrides": {tomatoes: 1, onion: 0.25}}
    )
    assert res.status_code == 200
    assert _pantry(conn, hid, "crushed tomatoes") == Decimal("1")
    assert _pantry(conn, hid, "yellow onion") == Decimal("0")
    assert _pantry(conn, hid, "rice") == Decimal("4")  # computed amount, no override

    assert client.get(f"/v1/meals/{meal_id}/cook-preview").json()["already_cooked"] is True


def test_http_rejects_negative_override(conn: psycopg.Connection, client: TestClient) -> None:
    owner, _, meal_id = _setup(conn)
    main.app.dependency_overrides[current_user] = lambda: owner
    res = client.post(
        f"/v1/meals/{meal_id}/cook", json={"overrides": {str(uuid.uuid4()): -1}}
    )
    assert res.status_code == 422


def test_http_preview_requires_membership(conn: psycopg.Connection, client: TestClient) -> None:
    _, _, meal_id = _setup(conn)
    main.app.dependency_overrides[current_user] = lambda: uuid.uuid4()
    assert client.get(f"/v1/meals/{meal_id}/cook-preview").status_code == 403
