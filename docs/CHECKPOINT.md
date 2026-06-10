# Project Checkpoint

> **Last Updated:** 2026-06-03
> Purpose: orient a fresh session quickly. Read this first, then the docs it points to.

## What Mise is
A cross-platform (web + mobile) AI meal planning app with a premium brand.
Core loop: AI meal plan → pantry-aware, budget-bound shopping list → shop → cook → deplete pantry → repeat.
Name from *mise en place*. Full vision in `docs/PRODUCT_SPEC.md`.

## Repo
- Local: `~/Documents/github/Mise`  (this is the intended working dir — launch new sessions here)
- Remote: https://github.com/brian-dev/Mise  (branch `main`)
- NOTE: early docs were drafted by mistake in a separate `Slipstream` repo, then moved here. Slipstream is unrelated.

## Done so far (all committed & pushed)
1. `docs/PRODUCT_SPEC.md` — product spec: vision, users, features, data model, stack, monetization, v1–v3 roadmap.
2. `docs/ARCHITECTURE.md` — system architecture: Supabase (system of record + RLS) + FastAPI AI service; JWT auth; async generation jobs via Realtime; pricing pipeline; monorepo layout; deployment.
3. `supabase/migrations/0001_schema.sql` — full schema + enums + indexes + one-active-plan-per-household constraint + updated_at triggers + `generation_jobs` table.
4. `supabase/migrations/0002_rls.sql` — RLS on the household-membership model; `is_household_member`/`is_household_owner` SECURITY DEFINER helpers.
5. `supabase/migrations/0003_auth_hooks.sql` — auto-create `public.users` profile on auth sign-up.
6. `supabase/seed/ingredients.sql` — ~40 starter ingredients with placeholder baseline prices.
7. `supabase/config.toml` — Supabase CLI config; seed via `./seed/*.sql`; analytics off (Colima vz). (committed 2cbab6d)
8. `docs/AI_LAYER.md` — AI generation design: one-shot full-plan tool-use schema, prompt layering w/ caching, ingredient canonicalization (pg_trgm ≥0.6), validation/repair, persistence mapping, pricing fallback, model selection, token-cost benchmark plan.
9. Monorepo scaffold (pnpm + Turborepo): `apps/web` (Next 14), `apps/mobile` (Expo SDK 52), `apps/ai-service` (FastAPI/uv via package.json shim), `packages/shared` (`@mise/shared` — enums + AI contract types mirroring the schema). Validated: `turbo run typecheck` green across all 5 tasks; `pnpm install` + `uv sync` clean; ai-service pytest+ruff pass.

## Validated (2026-06-04)
- Migrations + seed now run cleanly against a local Supabase stack. Confirmed in the live DB:
  13 public tables, RLS enabled on all 13, `is_household_member`/`is_household_owner` present,
  42 ingredients seeded, migration history 0001→0003.
- Local tooling setup (this machine had only Rosetta/x86 Homebrew + unaccepted Xcode license):
  - Supabase CLI installed to `~/.local/share/supabase` (shim + `supabase-go`), on PATH via `~/.zshrc`.
  - Native arm64 Homebrew installed at `/opt/homebrew` (the x86 `/usr/local` brew produced an x86 `limactl` that won't run on arm64). `brew shellenv` added to `~/.zprofile`.
  - `colima` + `docker` + `lima` installed natively; Colima runs with the **vz** backend.
  - `supabase init` generated `supabase/config.toml`; seed wired via `sql_paths = ["./seed/*.sql"]`.
  - `[analytics] enabled = false` — the `vector` container bind-mounts the docker socket, which Colima's vz/virtiofs backend can't do ("operation not supported"). Disabled; not needed locally.
- Start the stack: `colima start --vm-type vz && cd ~/Documents/github/Mise && supabase start`.

## Testing conventions (rule — see CLAUDE.md → Testing)
- Project must support **both API and UI testing** with standard tools; **no test leaves DB residue**.
- API: pytest. Canonical self-cleaning fixture `conn` in `apps/ai-service/tests/conftest.py`
  (rolled-back transaction); DB tests use the `db` marker; `live` marker for real Claude.
- UI: Vitest + React Testing Library (component) and Playwright (E2E) — seed + tear down own data.
- Manual/exploratory writes (curl, `scripts/seed_demo.py`, UI clicks) commit real rows — clean with
  **`pnpm db:reset`** (`scripts/db-reset.sh` → `supabase db reset`). Verified: full `turbo run test`
  leaves the dev DB at 0 households / 42 seeded ingredients (no pollution).

## Tech stack (decided)
Next.js (web) · Expo/React Native (mobile) · `@mise/shared` TS package · Supabase (Postgres/Auth/Storage/RLS) · FastAPI + Claude API (AI service) · USDA price data · Open Food Facts (barcode). Monorepo: pnpm + Turborepo.

## Next steps (in order)
1. ~~Supabase CLI config so `supabase start` applies migrations + seed automatically.~~ ✅ Done 2026-06-04 (see Validated section).
2. ~~AI layer design (prompt + structured-output schema).~~ ✅ Done 2026-06-04 → `docs/AI_LAYER.md`.
3. ~~Monorepo scaffolding (pnpm + Turborepo).~~ ✅ Done 2026-06-04.
4. **Build v1 core loop** (in progress): auth → household → generate plan → shopping list → pantry → cook/deplete.
   - ✅ Meal-plan generation core (`apps/ai-service`, merged #2): prompt + `emit_meal_plan`
     forced-tool schema, prompt caching on system+tool, validation + one repair retry,
     token-usage capture, `POST /v1/meal-plans/generate`. Offline tests pass (stubbed Claude).
     ⚠️ Generation NOT yet verified against the live Claude API — this env has only empty key
     placeholders; `live`-marked test needs a real ANTHROPIC_API_KEY (`uv run pytest -m live`).
   - ✅ Canonicalization + persistence (`db.py`, branch `feat/meal-plan-persistence`): pg_trgm
     ingredient match (≥0.6 reuse, else insert), transactional persist of plan→days→meals→
     recipes→recipe_ingredients with in-plan recipe de-dup. **Verified against the live local
     Postgres** (`db`-marked test, rolled back). Endpoint now persists and returns `meal_plan_id`.
   - ✅ Shopping-list builder (`shopping.py`, branch `feat/shopping-list-builder`): aggregates
     required quantities (scaled by servings/default_servings), subtracts pantry, prices against
     the USDA baseline (unit-matched; null when unit mismatch or no price), writes
     shopping_lists + items, reconciles vs budget. `POST /v1/shopping-lists/build`. **Verified
     against the live local Postgres** (rolled-back `db` test: pantry subtraction, pricing, over-budget).
   - ✅ Pantry depletion on cook (`pantry.py`, branch `feat/pantry-depletion`): marking a meal
     cooked sets `cooked_at` and, in `auto` mode, deducts `qty × servings/default_servings` from
     pantry (floored at 0), with per-ingredient partial-use overrides; `manual` mode marks cooked
     only. `POST /v1/meals/{id}/cook`. **Verified against the live local Postgres** (rolled-back
     `db` tests: auto scaling, manual no-op, override, already-cooked guard).
   - ✅ Web verification harness (`apps/web`, branch `feat/web-verification-harness`): minimal
     Next.js page driving the whole loop (household → generate → plan → cook → shopping list)
     against the AI service. Added CORS + read/helper endpoints (`GET/POST /v1/households`,
     `GET …/pantry`, `GET /v1/meal-plans/{id}`, `GET /v1/shopping-lists/{id}`). **Verified in a
     real browser**: page renders, browser→API fetch works (CORS), households + pantry load and
     reflect depletion. Generate path is wired identically but needs a real key to exercise.
     Dev harness only — not the auth'd production client.
   - ✅ Purchase → pantry restock (`shopping.py` `mark_purchased`, branch
     `feat/shopping-purchase-restock`): marking a list purchased adds each item's quantity to the
     pantry (upsert by ingredient+unit) and sets status `purchased`; double-purchase guarded.
     `POST /v1/shopping-lists/{id}/purchase`; web harness has a "Mark purchased" button.
     **Verified against live Postgres** (rolled-back test) and over HTTP. This closes the full
     pantry cycle: shop → purchase (restock) → cook (deplete) → repeat.
   - ✅ Async generation jobs (branch `feat/async-generation-jobs`): `POST /v1/meal-plans/generate`
     now returns `202 {job_id}` immediately and runs generation in a FastAPI background task that
     updates a `generation_jobs` row (queued→running→done/failed); `GET /v1/jobs/{id}` for status.
     Web harness polls the job and shows queued/running progress instead of a blocking spinner.
     Migration `0004` makes `generation_jobs.requested_by` nullable (pre-auth). **Verified**: job
     lifecycle over HTTP (202→running→failed w/o key) and the polling UI in a browser (status +
     error surfaced). Realtime push (vs polling) is a later enhancement.
   - ⏳ Auth — part (a) backend (branch `feat/auth-jwt-backend`): AI service verifies Supabase
     HS256 JWTs (`auth.py`), derives the user from `sub`, and authorizes household membership in
     code (ARCHITECTURE §4). Gated by `settings.require_auth` (default **off** so the no-login
     harness keeps working); the mechanism is fully built + tested. `create_household` adds the
     creator as owner; `list_households` scopes to the user. **Verified**: JWT verification
     (wrong secret/aud/expired → 401), membership isolation test (live PG), and HTTP enforcement
     with `require_auth=true` (no-token 401 / member 200 / non-member 403 / scoped listing).
     (Merged #11.)
   - ✅ Auth — part (b) step 1: endpoint coverage (branch `feat/auth-cover-endpoints`). The
     indirect/parent-scoped endpoints now resolve the owning household
     (`household_for_meal_plan/shopping_list/meal` in `db.py`) and enforce membership:
     meal-plan GET, shopping-list GET, shopping build, purchase, cook. **Verified**: resolver +
     cross-member rejection test (live PG), and HTTP enforcement on `cook` with `require_auth=true`
     (no-token 401 / non-member 403 / member 200 / already-cooked 409). Every household-scoped
     endpoint is now membership-checked — safe to flip enforcement on in step 2.
     Also: live Claude generation test now **passes against real Claude** (key in `.env`); `live`
     marker is excluded from the default `pytest` run (paid).
   - ✅ Auth — part (b) step 2: web login + enforcement ON (branch `feat/auth-web-login`).
     `apps/web` now uses `@supabase/supabase-js`: email/password sign in+up (`app/auth.tsx`),
     the page is gated behind a session, and `lib/api.ts` attaches the Supabase access token to
     every request. `require_auth` now defaults **true**. Key fix: Supabase signs user tokens
     with **ES256 via JWKS** (not the HS256 shared secret), so `auth.py` verifies both —
     HS256 (legacy/tests) and ES256/RS256 (real user tokens, `PyJWKClient` against the JWKS
     endpoint; needs `pyjwt[crypto]`). **Verified in a real browser**: sign-up → session →
     authed API calls → created a household with owner membership → membership-authorized
     pantry read (all 200s); unauthenticated request → 401.
   - ✅ Recipe swap (branch `feat/recipe-swap`, AI_LAYER §8): `POST /v1/meals/{id}/swap`
     regenerates one meal's recipe (Haiku via `emit_recipe` tool), constrained by dietary +
     pantry + the other plan titles (variety), persists the new recipe (shared pool,
     canonicalized) and points the meal at it. Web has a per-meal **Swap** button.
     **Verified**: live recipe generation against real Claude (`generate_recipe`), and a db test
     for `meal_swap_context` + `swap_meal_recipe` (rolled back). Also **fixed a test-infra bug**:
     the `conn` fixture now primes the outer transaction so `conn.transaction()` blocks become
     savepoints (a test leading with `create_household` was committing/leaking; now CLEAN).
   - ✅ Testability affordances + Playwright E2E (branch `feat/test-affordances`): test-only
     hooks behind `MISE_TEST_MODE` (`POST /v1/test/seed-plan` — household + ready plan, no Claude;
     `POST /v1/test/reset`), `data-testid` selectors across the UI, `GET
     /v1/households/{id}/latest-plan` so the UI shows an existing plan on selection (also a real
     UX win), and a Playwright scaffold (`apps/web/playwright.config.ts`, `e2e/loop.spec.ts`,
     `pnpm --filter @mise/web test:e2e`). **A passing E2E smoke test** drives sign up → seed →
     load plan → cook → build shopping list in ~2.4s with zero Claude calls. CLAUDE.md gains a
     "Build for testability" rule.
   - ✅ Pricing unit conversion (branch `feat/pricing-unit-conversion`, spec §3.6): `units.py`
     converts recipe quantities to the ingredient's USDA unit (mass↔mass, volume↔volume) so the
     shopping list prices items even when the units differ (e.g., 32 oz onion → $1.80 against a
     per-lb baseline). Count units / cross-dimension stay unpriced (AI fallback next). Target is a
     rough ±10% estimate, not precision. **Verified**: offline conversion tests + a shopping db
     test (rolled back). 27 tests pass.
   - ✅ AI pricing fallback (branch `feat/ai-pricing-fallback`, AI_LAYER §9): `pricing.py` +
     `POST /v1/shopping-lists/{id}/estimate-prices` fills prices for items the USDA path couldn't
     (count units, cross-dimension, unknown ingredients) using Haiku + a forced `emit_prices`
     tool that reasons in typical U.S. retail packaging terms. Web has an "Estimate remaining
     prices (AI)" button shown when items are unpriced. **Verified live**: garlic 3 cloves→$0.10,
     1 can tomatoes→$1.20, 1 cup milk→$0.50 (sensible). Offline + db tests pass (31).
   - TODO next: per-household price calibration (spec §3.6 — anchor prices to localize the
     baseline); a real retail pricing source for v2 (see note below); parallel/streaming
     generation; Supabase Realtime; recipe *iterate*; token-cost benchmark (AI_LAYER §11).
   - ✅ Pricing tiering decided (2026-06; docs `ARCHITECTURE §7`, `PRODUCT_SPEC §3.6/§6.1`,
     memory `pricing-tiers`): **free tier** = USDA + unit conversion + AI estimate (built, the
     default). **Paid tier** = real-retail sources — **Spoonacular** (recipe costing) +
     **Open Prices** (barcode). Dev keeps Spoonacular within its **free-tier quota**.
   - ✅ Spoonacular paid-tier provider (branch `feat/spoonacular-pricing`): `spoonacular.py` calls
     `parseIngredients` (one batched call, returns `estimatedCost` in cents) for real-retail prices;
     `pricing.resolve_prices` is the seam — Spoonacular first when `SPOONACULAR_API_KEY` is set, AI
     estimate for misses; free tier (no key) = AI only. `estimate-prices` now returns a `sources`
     breakdown. Short in-memory cache (1h, no permanent storage) keeps within the free dev quota.
     **Verified live**: onion 2 lb→$2.00, garlic 3 cloves→$0.20, tomatoes 1 can→$0.51 [spoonacular];
     cache reuse confirmed. 37 tests pass (offline + seam; 1 live spoonacular deselected).
   - ✅ Realtime job updates (branch `feat/realtime-jobs`): the web client now waits for generation
     via a **Supabase Realtime** subscription on the `generation_jobs` row (`lib/jobs.ts`
     `waitForJob`) instead of polling. Migration `0005` adds the table to the `supabase_realtime`
     publication + `replica identity full`; RLS (`generation_jobs_select_member`, already present)
     means a user only receives their own household's job changes; the socket is authed via
     `realtime.setAuth(token)`. A catch-up `getJob` on SUBSCRIBED handles the finished-before-
     subscribe race. **Verified in a real browser**: a 3-day plan generated end-to-end — button
     showed `running` then the plan rendered, driven only by Realtime (no polling). 0005 applies
     from a fresh `db reset`.
   - ✅ Faster generation (parallel per-day) (branch `feat/parallel-generation`): for multi-day
     plans, `generate_meal_plan` fans out one single-day generation per day concurrently
     (`ThreadPoolExecutor`) and merges, reusing the validated one-shot path. Config
     `parallel_generation` (default on). Each concurrent day gets a rotating **cuisine_hint** so
     days stay distinct (independent calls otherwise converge — saw 3 near-identical meals
     without it). **Verified live**: 3-day plan 31s→~20s (~1.6x) with good variety
     (Italian→Mexican→Indian). 38 tests pass.
   - TODO next: recipe *iterate*, Open Prices / barcode pantry, token-cost benchmark
     (AI_LAYER §11), Android.
   - Android: Expo Go on a physical device can point at the same API (LAN IP + add origin to
     `cors_origins`); not built yet.

## Local toolchain (added 2026-06-04)
- pnpm 9.15.0 (via corepack), uv 0.11.19 (brew). Node 20 (nvm). Root `.npmrc` sets `node-linker=hoisted` (Expo/RN need a flat node_modules under pnpm).
- Run all: `pnpm install` then `pnpm exec turbo run <task>`. AI service: `cd apps/ai-service && uv sync`.
- `node_modules/`, `.venv/`, build outputs are gitignored (root `.gitignore`).

## Memory
Project facts persist in auto-memory under the Mise project (project_mise.md, user_profile.md).
