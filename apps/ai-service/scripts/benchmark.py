"""Token-cost benchmark for meal-plan generation (AI_LAYER §11).

Runs representative request profiles through the real generation pipeline,
captures token usage, and computes $/generation so the free-tier limit can be
set on data. Calls real Claude — costs a little money. Run with a key:

    uv run python scripts/benchmark.py

Prints a per-profile table and the blended cost + free-tier math.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from mise_ai.config import settings
from mise_ai.generation import MealPlanResult, generate_meal_plan
from mise_ai.schemas import MealPlanRequest

# Claude Sonnet 4.6 pricing ($/1M tokens) — the meal-plan model (AI_LAYER §10).
# Cache write = 1.25x input, cache read = 0.1x input.
IN = Decimal("3")
OUT = Decimal("15")
CACHE_WRITE = IN * Decimal("1.25")
CACHE_READ = IN * Decimal("0.1")
PER = Decimal("1000000")


@dataclass
class Profile:
    name: str
    start: str
    end: str
    household_size: int
    meal_types: list[str]
    flags: list[str]


PROFILES = [
    Profile("1-day dinner", "2026-06-10", "2026-06-10", 2, ["dinner"], []),
    Profile("3-day dinner (veg)", "2026-06-10", "2026-06-12", 2, ["dinner"], ["vegetarian"]),
    Profile("7-day dinner", "2026-06-10", "2026-06-16", 4, ["dinner"], []),
    Profile("3-day all meals", "2026-06-10", "2026-06-12", 4,
            ["breakfast", "lunch", "dinner"], []),
]


def _cost(r: MealPlanResult) -> tuple[int, int, int, int, Decimal]:
    inp = sum(u.input_tokens for u in r.usage)
    out = sum(u.output_tokens for u in r.usage)
    cw = sum(u.cache_creation_input_tokens for u in r.usage)
    cr = sum(u.cache_read_input_tokens for u in r.usage)
    dollars = (
        Decimal(inp) * IN
        + Decimal(cw) * CACHE_WRITE
        + Decimal(cr) * CACHE_READ
        + Decimal(out) * OUT
    ) / PER
    return inp, out, cw, cr, dollars.quantize(Decimal("0.0001"))


def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (apps/ai-service/.env) to run the benchmark.")

    print(f"model: {settings.meal_plan_model}  parallel: {settings.parallel_generation}\n")
    cols = ("profile", "days", "in", "cache_w", "cache_r", "out", "sec", "$/run")
    header = (
        f"{cols[0]:22} {cols[1]:>4} {cols[2]:>7} {cols[3]:>8} "
        f"{cols[4]:>8} {cols[5]:>6} {cols[6]:>5} {cols[7]:>8}"
    )
    print(header)
    print("-" * len(header))

    total = Decimal("0")
    for p in PROFILES:
        req = MealPlanRequest.model_validate({
            "household_id": "00000000-0000-0000-0000-000000000001",
            "start_date": p.start, "end_date": p.end,
            "household_size": p.household_size, "meal_types": p.meal_types,
            "dietary": {"flags": p.flags, "avoid_text": None},
        })
        days = (req.end_date - req.start_date).days + 1
        t0 = time.monotonic()
        r = generate_meal_plan(req)
        secs = time.monotonic() - t0
        inp, out, cw, cr, dollars = _cost(r)
        total += dollars
        print(
            f"{p.name:22} {days:>4} {inp:>7} {cw:>8} {cr:>8} "
            f"{out:>6} {secs:>5.1f} {f'${dollars}':>8}"
        )

    blended = (total / len(PROFILES)).quantize(Decimal("0.0001"))
    print("-" * len(header))
    print(f"\nblended $/generation : ${blended}")
    print(f"free tier (~5/month) : ${(blended * 5).quantize(Decimal('0.01'))}/user/month")


if __name__ == "__main__":
    main()
