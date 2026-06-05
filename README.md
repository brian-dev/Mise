# Mise

Cross-platform AI meal planner. Core loop: AI meal plan → pantry-aware,
budget-bound shopping list → shop → purchase (restock) → cook (deplete) → repeat.

- Product spec: [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- AI layer design: [`docs/AI_LAYER.md`](docs/AI_LAYER.md)
- Current state: [`docs/CHECKPOINT.md`](docs/CHECKPOINT.md)

## Run it locally (one command)

```sh
pnpm dev
```

That single command (`scripts/dev.sh`) does everything:

1. starts the **Colima** container runtime (if not already running),
2. starts the local **Supabase** stack — applies migrations + seed,
3. installs JS deps (`pnpm`) and Python deps (`uv`),
4. launches the **AI service** on http://localhost:8000 and the **web client** on
   http://localhost:3000.

Then open **http://localhost:3000**, **sign up** (any email + password — the local
stack auto-confirms, no email step), then click through: create a household →
Generate a plan → Cook meals (pantry depletes) → Build shopping list → Mark
purchased (pantry restocks). `Ctrl-C` stops the dev servers (Colima + Supabase
keep running in the background).

> The API now **requires auth** — every request carries your Supabase session
> token, and you only see households you belong to. Set `REQUIRE_AUTH=false` to
> disable enforcement for unauthenticated `curl` poking.

> **Generate** calls Claude, so it needs an API key. Put it in
> `apps/ai-service/.env` (`cp apps/ai-service/.env.example apps/ai-service/.env`,
> then set `ANTHROPIC_API_KEY=`). Get a key at https://console.anthropic.com.
> Everything *except* Generate works without one — see "No key?" below.

### First time only

`pnpm dev` expects these tools on the machine; if any is missing it tells you,
and the install steps are in [`docs/CHECKPOINT.md`](docs/CHECKPOINT.md):

- **Colima** + **docker** (container runtime) — `brew install colima docker`
- **Supabase CLI** — at `~/.local/share/supabase` (the script adds it to `PATH`)
- **uv** (Python) — `brew install uv`
- **pnpm** — `corepack enable pnpm`

### No key? Exercise the loop without Claude

The Generate step needs Claude, but you can seed a plan directly and drive the
rest of the loop from the UI:

```sh
cd apps/ai-service && uv run python scripts/seed_demo.py
```

Then pick that household in the web UI and use Cook / Build shopping list /
Mark purchased.

## Stopping / cleanup

- Dev servers: `Ctrl-C` in the `pnpm dev` terminal.
- Supabase stack: `supabase stop` (from the repo root).
- Container runtime: `colima stop`.

### Keep the dev database clean

Automated tests roll back their writes and never leave residue. **Manual/exploratory
testing** (curl, `scripts/seed_demo.py`, clicking through the UI) commits real rows — reset
to a pristine seeded state when you're done:

```sh
pnpm db:reset      # drops all data, re-applies migrations + seed
```

See [`CLAUDE.md`](CLAUDE.md) → Testing for the full convention (API tests with pytest +
rolled-back fixtures; UI tests with Vitest/RTL + Playwright; nothing leaves the DB dirty).

## Inspect the database

- Supabase Studio: http://localhost:54323
- psql: `docker exec -it supabase_db_Mise psql -U postgres -d postgres`

## More

- AI service details & API: [`apps/ai-service/README.md`](apps/ai-service/README.md)
- Web harness details: [`apps/web/README.md`](apps/web/README.md)

## Contributing

All work happens on a branch and lands via PR — never commit directly to `main`
(enforced by `.githooks/pre-push`; enable once with
`git config core.hooksPath .githooks`). See [`CLAUDE.md`](CLAUDE.md).
