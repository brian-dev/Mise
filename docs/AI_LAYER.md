# AI Layer Design: Mise

> Design for the AI generation layer of the FastAPI service (ARCHITECTURE §5).
> Covers prompt architecture, the structured-output (tool-use) contract, ingredient
> canonicalization, validation/repair, pricing estimation, and cost controls.
> Status: design. No code yet — this is the blueprint for `apps/ai-service`.

## Table of Contents
1. [Scope & Operations](#1-scope--operations)
2. [Generation Strategy (key decisions)](#2-generation-strategy-key-decisions)
3. [Prompt Architecture](#3-prompt-architecture)
4. [Structured Output Contract](#4-structured-output-contract)
5. [Ingredient Canonicalization](#5-ingredient-canonicalization)
6. [Validation & Repair](#6-validation--repair)
7. [Persistence Mapping](#7-persistence-mapping)
8. [Recipe Swap & Iteration](#8-recipe-swap--iteration)
9. [Pricing Estimation](#9-pricing-estimation)
10. [Cost Controls & Model Selection](#10-cost-controls--model-selection)
11. [Token-Cost Benchmark](#11-token-cost-benchmark)
12. [Open Questions](#12-open-questions)

---

## 1. Scope & Operations

The AI layer backs four operations (ARCHITECTURE §5 endpoints). Each runs as an
async **job** (`generation_jobs` row) except pricing, which is fast enough to be
synchronous:

| Operation | Endpoint | Job kind | Sync/Async |
|---|---|---|---|
| Generate full meal plan | `POST /v1/meal-plans/generate` | `meal_plan` | async (job) |
| Generate one recipe (slot swap) | `POST /v1/recipes/generate` | `recipe` | async (job) |
| Iterate a recipe ("spicier") | `POST /v1/recipes/{id}/iterate` | `recipe_iterate` | async (job) |
| Estimate prices | `POST /v1/pricing/estimate` | — | sync |

All four share one core: **build context → call Claude with a forced tool → validate
→ canonicalize → persist**. The sections below describe that core, then the
per-operation differences in §8–§9.

---

## 2. Generation Strategy (key decisions)

These are the load-bearing decisions; everything downstream follows from them.

**D1 — One-shot full plan with recipes inline.**
A meal-plan generation emits the *entire* plan in a single Claude call: every day,
every meal slot, each with a **complete recipe** (ingredients + quantities + units +
instructions). We do **not** generate a skeleton of titles first and fetch recipes
lazily.
*Why:* the shopping list and budget reconciliation (ARCHITECTURE §7) need full
ingredient quantities immediately after generation. A title-only skeleton would force
N follow-up calls before the core loop can price anything — more latency, more cost,
more failure surface. One structured call is simplest and matches the job model
(latency is hidden behind the async job + Realtime notification).

**D2 — Regeneration is per-meal, not per-plan.**
Overrides (spec §3.2) call `/v1/recipes/generate` for a single slot, constrained by
the rest of the plan as context ("the other dinners this week are X, Y — make
something different"). The full plan is never regenerated wholesale on an edit.

**D3 — The model emits ingredient *names*, not IDs.**
Claude has no knowledge of our `ingredients` UUIDs. It emits a canonical-ish name +
category + quantity + unit; the service resolves names to `ingredient_id` server-side
(§5). This keeps the prompt stable (cacheable) and avoids hallucinated IDs.

**D4 — Controlled unit vocabulary.**
Quantities use a fixed unit enum (below). This keeps depletion math
(`quantity × servings ÷ default_servings`, spec §3.4) and pantry de-duplication
(`unique (household_id, ingredient_id, unit)`) sane. Free-text units are the single
biggest source of downstream breakage, so we constrain them at the schema boundary.

```
Mass:    g, kg, oz, lb
Volume:  ml, l, tsp, tbsp, cup, fl_oz
Count:   unit (e.g., "2 eggs"), clove, slice, can, bunch, pinch
```

**D5 — Generated recipes land in the shared pool.**
`recipes.created_by_user_id = null`, `is_ai_generated = true`, `source_prompt` saved
for iteration (spec §3.3, schema `recipes`). User edits fork a copy (handled at the
app layer, not here).

---

## 3. Prompt Architecture

Three layers, ordered by volatility so the stable prefix is **prompt-cached** (5-min
TTL; see ARCHITECTURE §5 "Cost controls"):

```
┌─ system (cache_control: ephemeral) ──────────────────────────┐
│  Role, hard rules, the unit vocabulary, canonicalization      │
│  guidance, "use pantry first" directive, output discipline.   │
│  Identical across all meal-plan generations → near-100% cache │
│  hit after the first call in a window.                        │
├─ tools (cache_control: ephemeral) ───────────────────────────┤
│  The emit_meal_plan tool schema (§4). Large + stable → cached.│
├─ user message (dynamic, not cached) ─────────────────────────┤
│  Compact JSON context block:                                  │
│    - date_range { start, end }, household_size (servings)     │
│    - meal_types requested [breakfast,lunch,dinner,snack]      │
│    - dietary { flags[], avoid_text } (user ∪ household §3.7)  │
│    - pantry [ {name, quantity, unit} ]  ← "use these first"   │
│    - budget (for the period), region, store_preference        │
│    - variety_target (e.g., "no repeated cuisine 2 days run")  │
└───────────────────────────────────────────────────────────────┘
```

Tool choice is **forced** (`tool_choice: {type: "tool", name: "emit_meal_plan"}`) so
the model must return structured data — no prose, no preamble.

Dietary handling: structured `flags` become hard constraints stated explicitly in the
user block ("MUST be gluten-free"); `avoid_text` is passed verbatim as a soft
preference. Household-level allergy overrides are merged into `flags` as hard
constraints before the call.

---

## 4. Structured Output Contract

One tool, `emit_meal_plan`. Shape mirrors the data model (`meal_plan_days → meals →
recipe → recipe_ingredients`). The model fills recipe content; the service owns IDs,
pricing, and persistence.

```jsonc
{
  "name": "emit_meal_plan",
  "description": "Emit a complete meal plan for the requested date range.",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["days"],
    "properties": {
      "days": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": false,
          "required": ["date", "meals"],
          "properties": {
            "date": { "type": "string", "format": "date" },
            "meals": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["meal_type", "recipe"],
                "properties": {
                  "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"]
                  },
                  "servings": { "type": "integer", "minimum": 1 },
                  "recipe": { "$ref": "#/$defs/recipe" }
                }
              }
            }
          }
        }
      }
    },
    "$defs": {
      "recipe": {
        "type": "object",
        "additionalProperties": false,
        "required": ["title", "cuisine_tags", "default_servings",
                     "instructions", "ingredients"],
        "properties": {
          "title":            { "type": "string" },
          "description":      { "type": "string" },
          "cuisine_tags":     { "type": "array", "items": { "type": "string" } },
          "prep_time":        { "type": "integer", "minimum": 0 },
          "cook_time":        { "type": "integer", "minimum": 0 },
          "default_servings": { "type": "integer", "minimum": 1 },
          "instructions":     { "type": "string" },
          "ingredients": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["name", "quantity", "unit"],
              "properties": {
                "name":     { "type": "string" },
                "category": { "type": "string" },
                "quantity": { "type": "number", "exclusiveMinimum": 0 },
                "unit": {
                  "type": "string",
                  "enum": ["g","kg","oz","lb","ml","l","tsp","tbsp","cup",
                           "fl_oz","unit","clove","slice","can","bunch","pinch"]
                },
                "is_optional": { "type": "boolean" }
              }
            }
          }
        }
      }
    }
  }
}
```

`meal_type`, `unit`, and `date` enums/formats map 1:1 to the Postgres `meal_type`
enum and the §D4 vocabulary. The recipe object maps to `recipes` +
`recipe_ingredients`.

The `recipe` `$def` is reused verbatim by `/v1/recipes/generate` and
`/v1/recipes/{id}/iterate` (those tools emit a single `recipe`, not a `days` array).

---

## 5. Ingredient Canonicalization

The model emits names; we resolve to `ingredients.id`. Pipeline per emitted
ingredient (uses the `pg_trgm` GIN index already in schema, `ingredients_name_trgm_idx`):

```
1. Normalize: lowercase, trim, singularize obvious plurals, strip descriptors
   ("fresh", "chopped", "large") into a canonical core noun.
2. Exact match on ingredients.name (case-insensitive) → use that id.
3. Else fuzzy: SELECT id, name, similarity(name, :q) AS sim
   FROM ingredients WHERE name % :q ORDER BY sim DESC LIMIT 1;
   - sim ≥ 0.6  → reuse existing id (canonical name wins; emitted name discarded).
   - sim < 0.6  → INSERT new ingredient (name=canonical, category=emitted,
                  usda_price_per_unit=null, last_usda_sync=null).
4. Newly inserted ingredients get priced on the next USDA Sync Job
   (ARCHITECTURE §7); until then they carry null price and surface as
   "price unknown" in budget reconciliation.
```

`pg_trgm`'s `%` operator threshold defaults to 0.3; we apply a stricter 0.6 in
application code to avoid bad merges ("chicken breast" vs "chicken broth"). The 0.6
cutoff is a starting point — tune against the benchmark (§11).

Canonicalization runs inside the persistence transaction so a concurrent generation
can't create duplicate ingredient rows; rely on the `ingredients.name unique`
constraint + `ON CONFLICT (name) DO NOTHING ... RETURNING` to make inserts idempotent.

---

## 6. Validation & Repair

After the tool call returns, before persistence:

1. **Schema validation** — Pydantic models mirroring §4. Forced tool use makes
   well-formed JSON near-certain, but never trust it blind.
2. **Semantic checks** —
   - every requested date present exactly once; no extra dates;
   - each day covers the requested `meal_types`;
   - servings default to `household_size` when omitted;
   - units ∈ vocabulary (schema enforces, but double-check post-parse).
3. **One repair retry** — on failure, send the validation errors back to Claude in a
   follow-up turn ("the plan was missing 2025-06-12; emit the corrected plan") and
   re-validate **once**. A second failure fails the job
   (`generation_jobs.status='failed'`, `error` populated) rather than looping
   (cost guard).

Unit normalization (e.g., model emits `"tablespoon"` despite the enum) is coerced
where unambiguous before rejecting.

---

## 7. Persistence Mapping

On a validated plan, in one transaction (service-role connection; the service does
its own membership authz per ARCHITECTURE §4, §6):

```
meal_plans            ← one row: household_id, status='draft', start/end, budget
  meal_plan_days      ← one row per emitted day (unique meal_plan_id+date)
    meals             ← one row per slot: meal_type, servings, recipe_id
recipes               ← one row per distinct recipe (shared pool, is_ai_generated,
                        source_prompt = the user context block)
  recipe_ingredients  ← rows: (recipe_id, ingredient_id ←§5, quantity, unit, is_optional)
generation_jobs       ← result = { meal_plan_id }, status='done'
```

The plan is created as `status='draft'`; the user reviews, then activates it (which
trips the `meal_plans_one_active_per_household` partial unique index). The AI layer
never sets `active` — that's a deliberate user action in the app.

Recipe de-duplication within a single plan: if the model emits the same recipe twice
(e.g., leftovers), insert the recipe once and point both `meals` at it.

---

## 8. Recipe Swap & Iteration

Both reuse the `recipe` `$def` (§4) with a single-recipe tool `emit_recipe`.

- **Swap** (`/v1/recipes/generate`): context includes the slot (meal_type, date,
  servings), dietary constraints, pantry, **and** the titles/cuisines of the other
  meals in the active plan so the swap adds variety rather than colliding.
- **Iterate** (`/v1/recipes/{id}/iterate`): load the existing recipe + its stored
  `source_prompt`, append the user's modifier ("spicier", "make it vegan", "use what
  I have"), emit a new recipe. Result is a **new** recipe row (shared pool); the app
  decides whether to swap it into the meal slot. Original is never mutated.

---

## 9. Pricing Estimation

`POST /v1/pricing/estimate` is the AI fallback in the pricing pipeline
(ARCHITECTURE §7), used when baseline confidence is low (new ingredients with null
USDA price, or a store/region with no calibration).

- Input: `{ items: [{name, unit}], region, store_preference }`.
- Synchronous (small output, no job row). Forced tool `emit_prices` →
  `[{name, unit, estimated_price, confidence}]`.
- Used as **fallback only**: the order of precedence stays calibrated-USDA-baseline →
  AI estimate (ARCHITECTURE §7 step 3). AI prices write back to
  `shopping_list_items.estimated_price`, never to `ingredients.usda_price_per_unit`
  (that column is reserved for the authoritative USDA sync).
- Budget reconciliation (sum vs `meal_plans.budget`, warn if over) stays in the
  shopping-list builder, not here — this endpoint only returns per-item prices.

Caching: region/store + ingredient prices change slowly; cache estimates per
`(ingredient_id, region, store)` with a TTL (e.g., 30 days) to avoid re-billing Claude
for the same lookup.

---

## 10. Cost Controls & Model Selection

LLM calls are the dominant variable cost and the free-tier lever (spec §6.1). Controls:

- **Prompt caching** on system + tool schema (§3). The stable prefix is large
  (tool schema is ~1–2k tokens); caching it cuts input cost on every call after the
  first in a 5-min window.
- **Per-token logging** — record input/uncached/cache-read/output tokens + model per
  job on `generation_jobs` (extend `result` jsonb, or a side `token_usage` table in a
  later migration). Feeds §11 and free-tier tuning.
- **Rate limiting** — enforced per user/household *before* the Claude call
  (ARCHITECTURE §5), so abuse never reaches the API. Free tier ≈ 5 generations/month
  (spec §6.1).
- **Bounded repair** — at most one repair retry (§6).

**Model selection (default; swappable per ARCHITECTURE §5):**

| Operation | Default model | Rationale |
|---|---|---|
| Meal plan (full) | Claude Sonnet 4.6 | Quality/coherence over a week of varied, constraint-satisfying meals justifies the cost. |
| Single recipe / iterate | Claude Haiku 4.5 | Small, well-scoped output; cheap + fast for interactive swaps. |
| Pricing estimate | Claude Haiku 4.5 | Numeric lookup, no long-form generation. |

Revisit after the benchmark (§11) — if Haiku holds plan quality, downgrade the plan
path to cut free-tier cost materially.

---

## 11. Token-Cost Benchmark

Goal: a defensible per-generation cost so the free-tier limit (~5/month) is set on
data, not a guess.

**Method.**
1. Assemble ~12 representative request profiles varying the cost drivers: plan length
   (3 / 7 / 14 days), meal_types per day (dinner-only vs all four), dietary
   constraints (none / vegetarian / multi-allergy), pantry size (empty vs stocked),
   household size (1 / 4).
2. Run each through `/v1/meal-plans/generate` against the live local stack; capture
   from the API response `usage`: `input_tokens`, `cache_creation_input_tokens`,
   `cache_read_input_tokens`, `output_tokens`.
3. Cost per run = `Σ(tokens × per-token rate for that bucket and model)`.
4. Report mean + p90 per profile, and a blended **cost-per-generation**.

**Free-tier math.**
```
free_tier_monthly_cost = cost_per_generation × 5
```
Compare against the Free→Personal upsell economics (spec §6.1). If
`free_tier_monthly_cost` is uncomfortable, the levers are: Haiku for the plan path,
shorter default plan length, or tightening the free limit below 5.

**Table to fill (post-implementation):**

| Profile | Days | Meals/day | Diet | Model | Input (cached/uncached) | Output | $/run |
|---|---|---|---|---|---|---|---|
| _tbd_ | | | | | | | |

This benchmark is a deliverable of the first AI-service implementation PR, not of this
design.

---

## 12. Open Questions

- **Canonicalization threshold (0.6):** validate against the benchmark corpus; measure
  false-merge vs duplicate-create rates and adjust.
- **Ingredient explosion:** AI may coin many near-synonyms before the catalog
  stabilizes. Do we need a periodic merge/cleanup job, or a curated allow-list the
  model is steered toward?
- **Pantry "use first" verification:** the prompt asks the model to prefer pantry
  items, but we don't currently *score* how well it did. Worth a post-gen metric
  (% of pantry ingredients used) to tune the prompt.
- **Streaming partial plans:** the job model allows it later (ARCHITECTURE §5); not in
  v1, but the day-array shape is stream-friendly if we want per-day progress.
- **Nutrition / calorie targets:** out of scope for v1 schema; would extend the recipe
  `$def` and context block if added.
