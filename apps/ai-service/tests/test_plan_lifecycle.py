"""Meal plan status lifecycle: draft → active → closed (spec §3.2).

Live Postgres via the rolled-back `conn` fixture. The HTTP tests route the app's
`connect()` onto the same fixture connection, so endpoint writes roll back too.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mise_ai import main
from mise_ai.auth import current_user
from mise_ai.db import create_household, persist_meal_plan
from mise_ai.plans import (
    PlanStateError,
    activate_plan,
    close_expired_plans,
    close_plan,
    current_meal_plan_id,
    ensure_active,
    ensure_open,
)
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

TODAY = date.today()


def _user(conn: psycopg.Connection) -> UUID:
    uid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid}@t.dev")
        )
    return uid


def _household(conn: psycopg.Connection, owner: UUID | None = None) -> UUID:
    return create_household(conn, "Lifecycle HH", owner_user_id=owner)["id"]


def _plan(conn: psycopg.Connection, household_id: UUID, day: date = TODAY) -> UUID:
    req = MealPlanRequest(
        household_id=household_id,
        start_date=day,
        end_date=day,
        household_size=2,
        meal_types=[MealType.dinner],
        budget=Decimal("40"),  # type: ignore[arg-type]
    )
    recipe = GeneratedRecipe(
        title=f"Dinner {uuid.uuid4().hex[:6]}",
        cuisine_tags=["american"],
        default_servings=2,
        instructions="Cook.",
        ingredients=[GeneratedIngredient(name="yellow onion", quantity=1, unit=Unit.lb)],
    )
    plan = GeneratedMealPlan(
        days=[
            GeneratedDay(
                date=day,
                meals=[GeneratedMeal(meal_type=MealType.dinner, servings=2, recipe=recipe)],
            )
        ]
    )
    pid = persist_meal_plan(conn, plan, req)
    # now() is frozen for the whole (rolled-back) test transaction; stamp the wall
    # clock so plans created in one test still order by creation like real ones.
    with conn.cursor() as cur:
        cur.execute(
            "update meal_plans set created_at = clock_timestamp() where id = %s", (pid,)
        )
    return pid


def _status(conn: psycopg.Connection, plan_id: UUID) -> tuple[str, bool]:
    with conn.cursor() as cur:
        cur.execute(
            "select status, closed_at is not null from meal_plans where id = %s", (plan_id,)
        )
        status, closed = cur.fetchone()  # type: ignore[misc]
    return status, closed


def _meal(conn: psycopg.Connection, plan_id: UUID) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "select m.id from meals m join meal_plan_days d on d.id = m.meal_plan_day_id "
            "where d.meal_plan_id = %s",
            (plan_id,),
        )
        return cur.fetchone()[0]  # type: ignore[index,no-any-return]


# ---- Domain logic ---------------------------------------------------------- #
def test_new_plan_is_draft_and_current(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    pid = _plan(conn, hid)
    assert _status(conn, pid) == ("draft", False)
    assert current_meal_plan_id(conn, hid) == pid


def test_activate_closes_previous_active(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    first = _plan(conn, hid)
    assert activate_plan(conn, first) is None
    assert _status(conn, first) == ("active", False)

    second = _plan(conn, hid)
    # The newer draft is the current plan even while the older one is active.
    assert current_meal_plan_id(conn, hid) == second
    assert activate_plan(conn, second) == first
    assert _status(conn, second) == ("active", False)
    assert _status(conn, first) == ("closed", True)


def test_activate_is_idempotent_and_rejects_closed(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    pid = _plan(conn, hid)
    activate_plan(conn, pid)
    assert activate_plan(conn, pid) is None  # already active -> no-op
    close_plan(conn, pid)
    with pytest.raises(PlanStateError):
        activate_plan(conn, pid)


def test_close_then_no_current_plan(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    pid = _plan(conn, hid)
    close_plan(conn, pid)  # a draft can be discarded directly
    assert _status(conn, pid) == ("closed", True)
    assert current_meal_plan_id(conn, hid) is None
    with pytest.raises(PlanStateError):
        close_plan(conn, pid)


def test_auto_close_after_grace(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    stale = _plan(conn, hid, TODAY - timedelta(days=3))  # a draft: stale drafts close too
    yesterday = _plan(conn, hid, TODAY - timedelta(days=1))
    activate_plan(conn, yesterday)

    assert close_expired_plans(conn, hid) == 1
    assert _status(conn, stale) == ("closed", True)
    # Ended yesterday: inside the one-day grace, still open.
    assert _status(conn, yesterday) == ("active", False)
    assert current_meal_plan_id(conn, hid) == yesterday


def test_activate_rejects_ended_draft(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    pid = _plan(conn, hid, TODAY - timedelta(days=5))
    with pytest.raises(PlanStateError):
        activate_plan(conn, pid)


def test_ensure_active_and_open(conn: psycopg.Connection) -> None:
    hid = _household(conn)
    pid = _plan(conn, hid)
    assert ensure_open(conn, pid) == "draft"
    ensure_active(conn, pid)
    assert _status(conn, pid)[0] == "active"
    close_plan(conn, pid)
    with pytest.raises(PlanStateError):
        ensure_open(conn, pid)
    with pytest.raises(PlanStateError):
        ensure_active(conn, pid)


# ---- HTTP ------------------------------------------------------------------ #
@pytest.fixture
def client(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App client whose DB work runs on the rolled-back fixture connection."""

    @contextmanager
    def _shared() -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(main, "connect", _shared)
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(current_user, None)


def _as(user: UUID) -> None:
    main.app.dependency_overrides[current_user] = lambda: user


def test_http_activate_and_close(conn: psycopg.Connection, client: TestClient) -> None:
    owner = _user(conn)
    hid = _household(conn, owner)
    pid = _plan(conn, hid)
    _as(owner)

    res = client.get(f"/v1/households/{hid}/latest-plan")
    assert res.status_code == 200 and res.json()["status"] == "draft"

    res = client.post(f"/v1/meal-plans/{pid}/activate")
    assert res.status_code == 200 and res.json()["status"] == "active"

    res = client.post(f"/v1/meal-plans/{pid}/close")
    assert res.status_code == 200 and res.json()["status"] == "closed"
    assert client.post(f"/v1/meal-plans/{pid}/close").status_code == 409
    assert client.post(f"/v1/meal-plans/{pid}/activate").status_code == 409
    # Closed plans drop out of the Plan tab and the dashboard.
    assert client.get(f"/v1/households/{hid}/latest-plan").status_code == 404
    assert client.get(f"/v1/households/{hid}/dashboard").json()["plan"] is None


def test_http_cook_activates_draft(conn: psycopg.Connection, client: TestClient) -> None:
    owner = _user(conn)
    hid = _household(conn, owner)
    pid = _plan(conn, hid)
    _as(owner)
    res = client.post(f"/v1/meals/{_meal(conn, pid)}/cook")
    assert res.status_code == 200
    assert _status(conn, pid)[0] == "active"


def test_http_shopping_build_activates_draft(
    conn: psycopg.Connection, client: TestClient
) -> None:
    owner = _user(conn)
    hid = _household(conn, owner)
    pid = _plan(conn, hid)
    _as(owner)
    res = client.post("/v1/shopping-lists/build", json={"meal_plan_id": str(pid)})
    assert res.status_code == 200
    assert _status(conn, pid)[0] == "active"


def test_http_closed_plan_is_read_only(conn: psycopg.Connection, client: TestClient) -> None:
    owner = _user(conn)
    hid = _household(conn, owner)
    pid = _plan(conn, hid)
    meal = _meal(conn, pid)
    close_plan(conn, pid)
    _as(owner)

    assert client.post(f"/v1/meals/{meal}/cook").status_code == 409
    assert client.delete(f"/v1/meals/{meal}").status_code == 409
    assert client.post(f"/v1/meals/{meal}/swap").status_code == 409
    assert (
        client.post(f"/v1/meals/{meal}/iterate", json={"modify": "spicier"}).status_code == 409
    )
    day = TODAY.isoformat()
    assert client.post(f"/v1/meal-plans/{pid}/days/{day}/regenerate").status_code == 409
    assert (
        client.post(f"/v1/meal-plans/{pid}/days/{day}/meals", json={}).status_code == 409
    )
    res = client.post("/v1/shopping-lists/build", json={"meal_plan_id": str(pid)})
    assert res.status_code == 409
    # Still readable for history.
    assert client.get(f"/v1/meal-plans/{pid}").json()["status"] == "closed"


def test_http_non_member_cannot_transition(
    conn: psycopg.Connection, client: TestClient
) -> None:
    owner, stranger = _user(conn), _user(conn)
    pid = _plan(conn, _household(conn, owner))
    _as(stranger)
    assert client.post(f"/v1/meal-plans/{pid}/activate").status_code == 403
    assert client.post(f"/v1/meal-plans/{pid}/close").status_code == 403
    assert _status(conn, pid)[0] == "draft"
