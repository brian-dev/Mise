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

## Not yet validated
- Migrations have NOT been run — no Postgres/Supabase CLI on the machine. Verify with:
  `brew install supabase/tap/supabase && cd ~/Documents/github/Mise && supabase init && supabase start`

## Tech stack (decided)
Next.js (web) · Expo/React Native (mobile) · `@mise/shared` TS package · Supabase (Postgres/Auth/Storage/RLS) · FastAPI + Claude API (AI service) · USDA price data · Open Food Facts (barcode). Monorepo: pnpm + Turborepo.

## Next steps (in order)
1. **AI layer design** ← next: prompt + structured-output (tool-use/JSON) schema for meal-plan generation; recipe iteration flow; token-cost benchmark to set free-tier limits.
2. Supabase CLI config (`config.toml` + `seed.sql` entrypoint) so `supabase start` applies migrations + seed automatically.
3. Monorepo scaffolding (`apps/web`, `apps/mobile`, `apps/ai-service`, `packages/shared`).
4. Build v1 core loop: auth → household → generate plan → shopping list → pantry → cook/deplete.

## Memory
Project facts persist in auto-memory under the Mise project (project_mise.md, user_profile.md).
