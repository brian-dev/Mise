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

## Tech stack (decided)
Next.js (web) · Expo/React Native (mobile) · `@mise/shared` TS package · Supabase (Postgres/Auth/Storage/RLS) · FastAPI + Claude API (AI service) · USDA price data · Open Food Facts (barcode). Monorepo: pnpm + Turborepo.

## Next steps (in order)
1. ~~Supabase CLI config so `supabase start` applies migrations + seed automatically.~~ ✅ Done 2026-06-04 (see Validated section).
2. **AI layer design** ← next: prompt + structured-output (tool-use/JSON) schema for meal-plan generation; recipe iteration flow; token-cost benchmark to set free-tier limits.
3. Monorepo scaffolding (`apps/web`, `apps/mobile`, `apps/ai-service`, `packages/shared`).
4. Build v1 core loop: auth → household → generate plan → shopping list → pantry → cook/deplete.

## Memory
Project facts persist in auto-memory under the Mise project (project_mise.md, user_profile.md).
