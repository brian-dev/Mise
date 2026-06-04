# Mise AI Service

FastAPI + Claude service for meal-plan generation, plus the DB-backed core-loop
operations (shopping list, pantry depletion). Design: `docs/AI_LAYER.md`,
`docs/ARCHITECTURE.md`.

## Prerequisites

- The local Supabase stack running (provides Postgres on `:54322`):
  ```sh
  colima start --vm-type vz          # container runtime
  cd <repo-root> && supabase start   # migrations + seed apply automatically
  ```
- `uv` (Python toolchain). From this directory: `uv sync`.

## Run the API

```sh
cd apps/ai-service
uv run uvicorn mise_ai.main:app --reload --port 8000
# or, from the repo root, via Turborepo:
#   pnpm exec turbo run dev --filter @mise/ai-service
```

Health check: `curl localhost:8000/v1/health` → `{"status":"ok"}`.
Interactive docs: http://localhost:8000/docs

## Endpoints (the v1 core loop)

| Method & path | What it does |
|---|---|
| `POST /v1/meal-plans/generate` | Generate a plan via Claude, validate, persist as draft. **Needs `ANTHROPIC_API_KEY`.** |
| `POST /v1/shopping-lists/build` | Aggregate plan → subtract pantry → price (USDA) → reconcile budget. DB only. |
| `POST /v1/meals/{meal_id}/cook` | Mark cooked; auto-mode deducts ingredients from the pantry. DB only. |

## Verify the workflows locally

### Without a Claude key (DB-backed steps)

Seed a demo household + plan, then drive the shopping-list and cook endpoints:

```sh
uv run python scripts/seed_demo.py     # prints meal_plan_id, meal_id, and curl commands
```

The script stocks 1 lb onion in the pantry and creates a 2-day plan (each dinner:
2 lb onion + 1 lb rice). Then:

```sh
# Shopping list: 4 lb onion required − 1 lb pantry = 3 lb @ $0.90 = $2.70 (rice unpriced)
curl -s -X POST localhost:8000/v1/shopping-lists/build \
  -H 'content-type: application/json' -d '{"meal_plan_id": "<MEAL_PLAN_ID>"}'

# Cook: deducts 2 lb onion (servings 4 / default 4) from the pantry
curl -s -X POST localhost:8000/v1/meals/<MEAL_ID>/cook \
  -H 'content-type: application/json' -d '{}'

# Cooking the same meal again returns HTTP 409
```

### With a Claude key (full generation)

```sh
export ANTHROPIC_API_KEY=sk-ant-...
curl -s -X POST localhost:8000/v1/meal-plans/generate \
  -H 'content-type: application/json' \
  -d '{
        "household_id": "<A REAL households.id>",
        "start_date": "2026-06-10",
        "end_date": "2026-06-12",
        "household_size": 2,
        "meal_types": ["dinner"],
        "dietary": {"flags": ["vegetarian"], "avoid_text": "no mushrooms"},
        "budget": 60
      }'
```

The response includes `meal_plan_id` (feed it to the shopping-list endpoint) and
per-call token `usage`.

## Tests

```sh
uv run pytest            # offline + db tests (db tests skip if Postgres is down)
uv run pytest -m db      # only the live-Postgres integration tests
uv run pytest -m live    # only the live-Claude test (needs ANTHROPIC_API_KEY)
uv run ruff check . && uv run mypy src
```

## Inspect the data

Supabase Studio (tables, rows): http://localhost:54323
Or psql: `docker exec -it supabase_db_Mise psql -U postgres -d postgres`
