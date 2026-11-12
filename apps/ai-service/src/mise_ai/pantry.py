"""Pantry depletion on cook (spec §3.4).

Marking a meal cooked optionally deducts its ingredients from the household
pantry. Deduction amount per ingredient:

    quantity_deducted = recipe_ingredient.quantity * (meal.servings / recipe.default_servings)

Behavior depends on the household's `pantry_depletion_mode`:
  * auto   -> deduct automatically on cook.
  * manual -> mark cooked only; the user removes items themselves.

Partial-use handling (spec §3.4): callers may pass per-ingredient `overrides`
(actual quantity used) to replace the computed amount. Pantry quantities never
go negative — if on-hand is less than the deduction, it floors at zero.

`cook_preview` lets the client ask *before* cooking which deductions deserve a
confirm (the "partial-use prompt"), so the common case stays one tap:

  * partial — a fractional amount of something you open whole (½ can, ½ onion,
              ⅓ bunch): what's left is a judgement call, so ask.
  * short   — the pantry holds less than the recipe needs; the deduction would
              floor at zero, so confirm what was actually used.

Only ingredients with a matching pantry row (same ingredient + unit) can be
deducted, so only those are listed as deductible or flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import psycopg


@dataclass
class Deduction:
    ingredient_id: UUID
    unit: str
    amount: Decimal


# Count units for things you open/use whole; a fractional amount means a
# leftover the user should confirm. (clove/slice/pinch fractions are noise.)
_WHOLE_UNITS = {"can", "unit", "bunch"}


@dataclass
class PreviewItem:
    ingredient_id: UUID
    name: str
    unit: str
    planned: Decimal
    on_hand: Decimal | None
    is_optional: bool
    reason: str | None  # "partial" | "short" | None (no confirm needed)


@dataclass
class CookPreview:
    meal_id: UUID
    mode: str
    servings: int
    already_cooked: bool
    ingredients: list[PreviewItem] = field(default_factory=list)


def _tidy(d: Decimal) -> Decimal:
    """Round to 3 places and drop trailing zeros without exponent notation
    (Decimal.normalize turns 100 into 1E+2)."""
    d = d.quantize(Decimal("0.001"))
    return d.to_integral_value() if d == d.to_integral_value() else d.normalize()


def _confirm_reason(unit: str, planned: Decimal, on_hand: Decimal | None) -> str | None:
    if on_hand is None:
        return None  # nothing stocked -> nothing to deduct -> nothing to confirm
    if on_hand < planned:
        return "short"
    if unit in _WHOLE_UNITS and planned != planned.to_integral_value():
        return "partial"
    return None


def cook_preview(conn: psycopg.Connection, meal_id: UUID) -> CookPreview:
    """What cooking this meal would deduct, flagging the amounts worth confirming.
    In manual mode nothing is deducted, so nothing is flagged."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select m.cooked_at, m.servings, m.recipe_id,
                   r.default_servings, mp.household_id, h.pantry_depletion_mode
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join meal_plans mp on mp.id = d.meal_plan_id
            join households h on h.id = mp.household_id
            join recipes r on r.id = m.recipe_id
            where m.id = %s
            """,
            (meal_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"meal {meal_id} not found (or has no recipe)")
        cooked_at, servings, recipe_id, default_servings, household_id, mode = row
        factor = Decimal(servings) / Decimal(default_servings)
        cur.execute(
            """
            select ri.ingredient_id, i.name, ri.unit, ri.quantity, ri.is_optional, p.quantity
            from recipe_ingredients ri
            join ingredients i on i.id = ri.ingredient_id
            left join pantry_items p
              on p.household_id = %s
             and p.ingredient_id = ri.ingredient_id
             and p.unit = ri.unit
            where ri.recipe_id = %s
            order by ri.is_optional, i.name
            """,
            (household_id, recipe_id),
        )
        items = []
        for ingredient_id, name, unit, quantity, is_optional, on_hand in cur.fetchall():
            planned = _tidy(quantity * factor)
            items.append(
                PreviewItem(
                    ingredient_id=ingredient_id,
                    name=name,
                    unit=unit,
                    planned=planned,
                    on_hand=on_hand,
                    is_optional=is_optional,
                    reason=_confirm_reason(unit, planned, on_hand) if mode == "auto" else None,
                )
            )
    return CookPreview(
        meal_id=meal_id,
        mode=mode,
        servings=servings,
        already_cooked=cooked_at is not None,
        ingredients=items,
    )


@dataclass
class CookResult:
    meal_id: UUID
    mode: str
    deductions: list[Deduction] = field(default_factory=list)


def cook_meal(
    conn: psycopg.Connection,
    meal_id: UUID,
    overrides: dict[UUID, Decimal] | None = None,
) -> CookResult:
    overrides = overrides or {}

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            select m.cooked_at, m.servings, m.recipe_id,
                   r.default_servings, mp.household_id, h.pantry_depletion_mode
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join meal_plans mp on mp.id = d.meal_plan_id
            join households h on h.id = mp.household_id
            join recipes r on r.id = m.recipe_id
            where m.id = %s
            """,
            (meal_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"meal {meal_id} not found (or has no recipe)")
        cooked_at, servings, recipe_id, default_servings, household_id, mode = row
        if cooked_at is not None:
            raise ValueError(f"meal {meal_id} is already cooked")

        cur.execute("update meals set cooked_at = now() where id = %s", (meal_id,))

        deductions: list[Deduction] = []
        if mode == "auto":
            factor = Decimal(servings) / Decimal(default_servings)
            cur.execute(
                """
                select ingredient_id, quantity, unit
                from recipe_ingredients
                where recipe_id = %s
                """,
                (recipe_id,),
            )
            for ingredient_id, quantity, unit in cur.fetchall():
                amount = overrides.get(ingredient_id, quantity * factor)
                # Deduct from the matching pantry row, flooring at zero. Nothing
                # on hand -> nothing to deduct.
                cur.execute(
                    """
                    update pantry_items
                    set quantity = greatest(0, quantity - %s)
                    where household_id = %s and ingredient_id = %s and unit = %s
                    """,
                    (amount, household_id, ingredient_id, unit),
                )
                if cur.rowcount:
                    deductions.append(Deduction(ingredient_id, unit, amount))

    return CookResult(meal_id=meal_id, mode=mode, deductions=deductions)
