# Mise Web (dev harness)

A minimal Next.js page to **verify the core loop end-to-end in a browser**:
select/create a household → generate a plan → build the shopping list → cook a
meal and watch the pantry deplete.

> This is a dev-verification harness, not the final client. It calls the AI
> service directly and has no auth. The production web client (Supabase auth +
> RLS-aware reads per `docs/ARCHITECTURE.md`) is a later build.

## Run it

1. Start the AI service + local Supabase stack (see `apps/ai-service/README.md`).
   Generation needs `ANTHROPIC_API_KEY` in `apps/ai-service/.env`.
2. Start the web app:
   ```sh
   pnpm --filter @mise/web dev      # http://localhost:3000
   ```
   The API base URL defaults to `http://localhost:8000`; override with
   `NEXT_PUBLIC_API_URL`.

## Flow

1. **Household** — pick an existing one or create a new one; its pantry is shown.
2. **Generate** — set the date range, meals, dietary prefs, and budget, then
   *Generate plan* (calls Claude; takes a few seconds).
3. **Plan** — see each day's meals; *Cook* a meal to deplete the pantry (auto mode).
4. **Shopping list** — *Build shopping list* to see pantry-subtracted, priced items.

## Notes

- Without a Claude key, you can still exercise everything except *Generate* by
  seeding a plan: `cd apps/ai-service && uv run python scripts/seed_demo.py`,
  then select that household in the UI.
- CORS for `localhost:3000` is configured on the AI service (`cors_origins`).
