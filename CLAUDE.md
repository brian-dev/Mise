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
