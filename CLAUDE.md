# Mise — Project Instructions

## Branching (required)
**All new work happens on a separate branch — never commit directly to `main`.**

- Before starting any change, create a branch off the latest `main`
  (e.g. `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`, `chore/<short-name>`).
- Commit the work there; land it on `main` via pull request, not by pushing to `main` directly.
- `main` stays clean and releasable at all times.
- The only exception is an explicit, one-off instruction from the user to commit to `main`.

**Enforcement:** a committed pre-push hook (`.githooks/pre-push`) blocks direct pushes to
`main`. Enable it once per clone:

```sh
git config core.hooksPath .githooks
```

This is client-side (bypassable with `git push --no-verify`). Server-side branch
protection needs GitHub Pro or a public repo — revisit if the repo goes Pro/public.

## Testing (required)
The project must support **both API and UI testing** using each ecosystem's standard
conventions, and **no test may leave residue** in the dev database.

**Cleanliness — the hard rule.** Anything that writes to the database while testing must
clean up after itself. Two acceptable patterns:
- **Automated tests:** wrap DB work in a transaction that is **rolled back** in teardown
  (the canonical `conn` fixture in `apps/ai-service/tests/conftest.py` — DB tests carry the
  `db` marker and `yield` a connection that is rolled back), or explicitly delete what they
  create. Never commit test rows.
- **Manual / exploratory checks** (curl, `scripts/seed_demo.py`, ad-hoc scripts): these
  intentionally commit, so treat them as disposable — reset the dev DB afterward with
  `pnpm db:reset` (re-applies migrations + seed → pristine). Don't accumulate demo rows.

**API testing (`apps/ai-service`):** pytest. Pure logic + FastAPI `TestClient` for endpoints;
integration tests run against the local Supabase stack via the rolled-back `conn` fixture and
the `db` marker (`uv run pytest -m db`). The `live` marker hits **real, paid** Claude and is
**excluded by default** (`addopts = -m 'not live'`); run it explicitly with `uv run pytest -m live`.

**UI testing (`apps/web`, `apps/mobile`):** standard React conventions — component/unit tests
with **Vitest + React Testing Library**, end-to-end with **Playwright**. UI/E2E tests must seed
and tear down their own data (or run against a freshly reset DB) and never leave rows behind.

**Build for testability (required).** As features are added, also add the affordances that make
them fast and reliable to test — especially for E2E/Playwright:
- **Test-only hooks behind a flag.** Operations that let a test reach an app state instantly and
  deterministically live under `/v1/test/*`, mounted only when `MISE_TEST_MODE=true` (never in
  prod). Today: `POST /v1/test/seed-plan` (create a household + ready plan for the caller, **no
  Claude**) and `POST /v1/test/reset` (delete the caller's data). Add more such hooks as needed.
- **Never call real Claude from E2E.** Seed via the hook (deterministic, free) instead of driving
  generation. Real-Claude coverage stays in the `live`-marked pytest tests.
- **Stable selectors.** UI elements tests interact with carry `data-testid` (don't rely on text
  or DOM structure).
- **Programmatic auth.** The local stack auto-confirms sign-ups, so E2E signs up a unique user
  per run and reads the Supabase session token from `localStorage` for API hooks.

**E2E (Playwright):** `apps/web/e2e/*.spec.ts`, run with `pnpm --filter @mise/web test:e2e`
(needs Supabase up + the AI service on :8000 started with `MISE_TEST_MODE=true`). Keep E2E out of
the default `turbo run test` (it needs running servers).

**Before merging:** `pnpm exec turbo run typecheck test` is green, and the dev DB row counts are
unchanged by the test run.

## Orientation
- Start a session by reading `docs/CHECKPOINT.md` — it points to the current state and the
  other design docs (`PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `AI_LAYER.md`).

## Toolchain
- JS: pnpm (via corepack) + Turborepo. Run tasks with `pnpm exec turbo run <task>`.
- Python (`apps/ai-service`): uv. `cd apps/ai-service && uv sync`, then `uv run <cmd>`.
- Local DB: Supabase CLI (`~/.local/share/supabase`) on Colima (`colima start --vm-type vz`).
  See `docs/CHECKPOINT.md` for the validated start sequence.
- Root `.npmrc` sets `node-linker=hoisted` (Expo/RN require a flat node_modules under pnpm) —
  do not remove.
