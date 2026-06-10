"""Shopping-list builder: meal plan -> required quantities -> pantry subtraction
-> pricing -> budget reconciliation (ARCHITECTURE §7, spec §3.5).

Pure database logic (no AI). Pricing uses the calibrated-USDA baseline; the
AI estimate fallback (AI_LAYER §9) is a follow-up. An item is priced only when
the recipe unit matches the ingredient's `usda_unit` and a baseline price
exists — otherwise it carries a null price ("price unknown") and is excluded
from the estimated total.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg

from .units import convert_quantity


@dataclass
class Restock:
    ingredient_id: UUID
    unit: str
    amount: Decimal


@dataclass
class PurchaseResult:
    shopping_list_id: UUID
    restocked: list[Restock]


@dataclass
class ShoppingListResult:
    shopping_list_id: UUID
    estimated_total: Decimal
    budget: Decimal | None
    over_budget: bool
    items_total: int
    items_priced: int

    @property
    def items_unpriced(self) -> int:
        return self.items_total - self.items_priced


def build_shopping_list(conn: psycopg.Connection, meal_plan_id: UUID) -> ShoppingListResult:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            select mp.household_id, mp.budget, h.store_preference
            from meal_plans mp
            join households h on h.id = mp.household_id
            where mp.id = %s
            """,
            (meal_plan_id,),
        )
        plan_row = cur.fetchone()
        if plan_row is None:
            raise ValueError(f"meal_plan {meal_plan_id} not found")
        household_id, budget, store_preference = plan_row

        # Aggregate required quantities across the plan, scaling each recipe
        # ingredient by the meal's servings vs the recipe's default servings.
        # Optional ingredients are excluded from the shopping list.
        cur.execute(
            """
            select ri.ingredient_id,
                   ri.unit,
                   sum(ri.quantity * m.servings::numeric / r.default_servings) as required
            from meals m
            join meal_plan_days d on d.id = m.meal_plan_day_id
            join recipes r on r.id = m.recipe_id
            join recipe_ingredients ri on ri.recipe_id = r.id
            where d.meal_plan_id = %s and ri.is_optional = false
            group by ri.ingredient_id, ri.unit
            """,
            (meal_plan_id,),
        )
        required_rows = cur.fetchall()

        cur.execute(
            """
            insert into shopping_lists (meal_plan_id, store_preference, status)
            values (%s, %s, 'draft')
            returning id
            """,
            (meal_plan_id, store_preference),
        )
        shopping_list_id: UUID = cur.fetchone()[0]  # type: ignore[index]

        estimated_total = Decimal("0")
        items_total = 0
        items_priced = 0

        for ingredient_id, unit, required in required_rows:
            # Subtract what the household already has (same ingredient + unit).
            cur.execute(
                """
                select quantity from pantry_items
                where household_id = %s and ingredient_id = %s and unit = %s
                """,
                (household_id, ingredient_id, unit),
            )
            pantry_row = cur.fetchone()
            on_hand = pantry_row[0] if pantry_row is not None else Decimal("0")
            needed = required - on_hand
            if needed <= 0:
                continue  # fully covered by the pantry

            # Price against the USDA baseline, converting the recipe unit into the
            # USDA unit where the dimensions are compatible (spec §3.6). Items that
            # can't be converted (count units, cross-dimension) or have no baseline
            # price stay unpriced — the AI estimate fallback (AI_LAYER §9) is next.
            cur.execute(
                "select usda_price_per_unit, usda_unit from ingredients where id = %s",
                (ingredient_id,),
            )
            price_row = cur.fetchone()
            price_per_unit, usda_unit = price_row if price_row else (None, None)
            estimated_price: Decimal | None = None
            if price_per_unit is not None and usda_unit is not None:
                converted = convert_quantity(needed, unit, usda_unit)
                if converted is not None:
                    estimated_price = (converted * price_per_unit).quantize(Decimal("0.01"))
                    estimated_total += estimated_price
                    items_priced += 1

            cur.execute(
                """
                insert into shopping_list_items
                  (shopping_list_id, ingredient_id, quantity_needed, unit,
                   estimated_price, source)
                values (%s, %s, %s, %s, %s, 'recipe')
                """,
                (shopping_list_id, ingredient_id, needed, unit, estimated_price),
            )
            items_total += 1

        cur.execute(
            "update shopping_lists set estimated_total = %s where id = %s",
            (estimated_total, shopping_list_id),
        )

    over_budget = budget is not None and estimated_total > budget
    return ShoppingListResult(
        shopping_list_id=shopping_list_id,
        estimated_total=estimated_total,
        budget=budget,
        over_budget=over_budget,
        items_total=items_total,
        items_priced=items_priced,
    )


def mark_purchased(conn: psycopg.Connection, shopping_list_id: UUID) -> PurchaseResult:
    """Mark a shopping list purchased and restock the pantry (spec §3.5).

    Each item's `quantity_needed` is added to the household pantry, matched by
    (ingredient, unit). Idempotent guard: a list can only be purchased once, so
    the pantry isn't double-restocked.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            select sl.status, mp.household_id
            from shopping_lists sl
            join meal_plans mp on mp.id = sl.meal_plan_id
            where sl.id = %s
            """,
            (shopping_list_id,),
        )
        head = cur.fetchone()
        if head is None:
            raise ValueError(f"shopping_list {shopping_list_id} not found")
        status, household_id = head
        if status == "purchased":
            raise ValueError(f"shopping_list {shopping_list_id} is already purchased")

        cur.execute(
            "select ingredient_id, quantity_needed, unit from shopping_list_items "
            "where shopping_list_id = %s",
            (shopping_list_id,),
        )
        restocked: list[Restock] = []
        for ingredient_id, quantity_needed, unit in cur.fetchall():
            # Add to the matching pantry row, or create it.
            cur.execute(
                """
                insert into pantry_items (household_id, ingredient_id, quantity, unit)
                values (%s, %s, %s, %s)
                on conflict (household_id, ingredient_id, unit)
                do update set quantity = pantry_items.quantity + excluded.quantity
                """,
                (household_id, ingredient_id, quantity_needed, unit),
            )
            restocked.append(Restock(ingredient_id, unit, quantity_needed))

        cur.execute(
            "update shopping_lists set status = 'purchased' where id = %s",
            (shopping_list_id,),
        )

    return PurchaseResult(shopping_list_id=shopping_list_id, restocked=restocked)
