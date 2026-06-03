# System Architecture: Mise

> **Status:** Planning Phase
> **Last Updated:** 2026-06-03
> **Version:** 0.1 (Pre-development)
> **Companion doc:** [PRODUCT_SPEC.md](./PRODUCT_SPEC.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [System Components](#2-system-components)
3. [Service Boundaries: Supabase vs. FastAPI](#3-service-boundaries-supabase-vs-fastapi)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [The AI Service](#5-the-ai-service)
6. [Data Access & Row Level Security](#6-data-access--row-level-security)
7. [Pricing & USDA Data Pipeline](#7-pricing--usda-data-pipeline)
8. [API Surface](#8-api-surface)
9. [Core Loop: End-to-End Request Flows](#9-core-loop-end-to-end-request-flows)
10. [Repository Structure](#10-repository-structure)
11. [Environments & Deployment](#11-environments--deployment)
12. [Cross-Cutting Concerns](#12-cross-cutting-concerns)
13. [Architectural Decisions & Trade-offs](#13-architectural-decisions--trade-offs)

---

## 1. Architecture Overview

Mise is a cross-platform app (web + mobile) backed by two server-side concerns:

- **Supabase** — the system of record: Postgres database, authentication, storage, and direct CRUD for standard data operations.
- **AI Service (FastAPI)** — a stateless Python service that owns all LLM interactions and AI-adjacent logic (meal plan generation, recipe iteration, AI-assisted pricing).

The clients talk **directly to Supabase** for routine reads/writes (guarded by Row Level Security) and to the **AI Service** for generation tasks. The AI Service uses the database too — it reads context (pantry, preferences) and writes generated results (recipes, meal plans).

```
        ┌────────────────────┐         ┌────────────────────┐
        │   Web (Next.js)    │         │ Mobile (Expo / RN) │
        └─────────┬──────────┘         └─────────┬──────────┘
                  │                               │
        ┌─────────┴───────────────────────────────┴─────────┐
        │              @mise/shared (TS types)               │
        └─────────┬───────────────────────────────┬─────────┘
                  │                               │
       direct CRUD│ (RLS-guarded)      generation │ requests
                  │                    (JWT-auth)  │
                  ▼                               ▼
        ┌────────────────────┐         ┌────────────────────┐
        │     Supabase       │◄────────│  AI Service        │
        │  Postgres + Auth   │ reads/  │  (FastAPI, Python) │
        │  + Storage + RLS   │ writes  │  + Claude API      │
        └────────────────────┘         └─────────┬──────────┘
                  ▲                               │
                  │                               ▼
        ┌─────────┴──────────┐         ┌────────────────────┐
        │  USDA Sync Job     │         │   Claude API       │
        │  (scheduled)       │         │   (Anthropic)      │
        └────────────────────┘         └────────────────────┘
```

**Guiding principle:** keep the AI Service stateless and narrow. It does AI work and persists results; it is *not* a general-purpose backend. Everything that is plain CRUD goes straight to Supabase. This minimizes the surface area we have to build, host, and secure.

---

## 2. System Components

| Component | Tech | Responsibility |
|---|---|---|
| **Web client** | Next.js (TypeScript) | Full-featured web app; SSR for marketing/landing, client-side app shell |
| **Mobile client** | Expo / React Native (TypeScript) | Native iOS/Android app with feature parity; barcode scanning via Expo Camera |
| **Shared package** | TypeScript | Shared types, API contracts, validation schemas (Zod), domain constants |
| **Supabase** | Postgres, GoTrue auth, Storage | System of record, auth, file storage, real-time, RLS enforcement |
| **AI Service** | FastAPI (Python) | LLM orchestration, meal-plan/recipe generation, AI price estimation |
| **USDA Sync Job** | Python (scheduled) | Periodically refresh ingredient baseline pricing from USDA data |
| **Claude API** | Anthropic | LLM provider (abstracted behind the AI Service) |

---

## 3. Service Boundaries: Supabase vs. FastAPI

The single most important architectural decision: **what goes where.**

### Goes to Supabase (direct from clients)
- Auth (sign up, sign in, session refresh)
- Reading/writing households, members, meal plans, meals, pantry items, shopping lists
- Toggling state: mark meal cooked, check off shopping item, finalize a list
- Reading recipes (shared pool + user-owned)
- Storage (e.g., recipe images later)

These are simple, high-frequency operations. Routing them through a custom backend would add latency and code for no benefit. **Row Level Security** (Section 6) makes direct access safe.

### Goes to the AI Service (FastAPI)
- **Meal plan generation** — the big one: takes a date range + context, returns a populated plan
- **Recipe (re)generation & iteration** — "make this spicier," "something similar," single-recipe swaps
- **AI-assisted price estimation** — regional/store-aware estimates beyond the USDA baseline
- Anything requiring an LLM API key (must never touch the client) or non-trivial server-side orchestration

### Why a separate service at all (vs. Supabase Edge Functions)?
- LLM work is **Python-friendly** (Anthropic SDK, prompt tooling, validation libs)
- Generation can be **long-running**; we want control over timeouts, retries, streaming, and job semantics that are awkward in edge functions
- Keeps the LLM provider **swappable** and the prompt logic **testable** in isolation
- Edge Functions remain an option for tiny glue tasks if needed

---

## 4. Authentication & Authorization

**Provider:** Supabase Auth (GoTrue), email/password for v1 (OAuth providers can be added later).

**Token flow:**
1. Client authenticates with Supabase → receives a **JWT** (access + refresh tokens).
2. For direct Supabase calls, the JWT is attached automatically by the Supabase client SDK; **RLS** policies enforce per-row access.
3. For AI Service calls, the client sends the **same Supabase JWT** as a `Bearer` token.
4. The AI Service **verifies the JWT** against Supabase's JWKS/public key, extracts the `user_id`, and authorizes the request (e.g., confirms the user is a member of the household they're generating a plan for).

**Key rule:** the AI Service never trusts a `user_id`/`household_id` from the request body alone — it derives identity from the verified JWT and checks membership before acting.

```
Client ──(Supabase JWT)──► AI Service
                              │ verify JWT (JWKS)
                              │ extract user_id
                              │ check household membership
                              ▼
                        proceed / 403
```

---

## 5. The AI Service

### Responsibilities
- Build prompts from structured context (preferences, pantry, budget, date range)
- Call Claude with **structured output** (tool use / JSON schema) so results map to the data model
- Validate + normalize LLM output (units, ingredient name canonicalization)
- Persist generated recipes/plans to Postgres
- Estimate pricing and reconcile against budget

### Endpoints (initial)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/meal-plans/generate` | Generate a full meal plan for a household + date range |
| `POST` | `/v1/recipes/generate` | Generate a single recipe (for a meal slot swap) |
| `POST` | `/v1/recipes/{id}/iterate` | Iterate on an existing recipe ("spicier", "similar") |
| `POST` | `/v1/pricing/estimate` | AI-assisted regional/store price estimate for items |
| `GET` | `/v1/health` | Liveness/readiness probe |

### Generation as a job (not a blocking call)
Meal plan generation can take many seconds. To keep clients responsive and avoid HTTP timeouts:

1. Client `POST`s a generation request → service creates a **job row** (`status: queued`) and returns a `job_id` immediately (`202 Accepted`).
2. The service processes the job (calls Claude, validates, persists).
3. Client learns of completion via **Supabase Realtime** subscription on the job row (preferred) or polling `GET /v1/jobs/{id}`.

This pattern also gives us natural retry, observability, and the ability to stream partial progress later.

### Structured output contract
The LLM is constrained to emit JSON matching our schema: a meal plan as days → meals → recipes → ingredients, with quantities, units, servings, and cuisine tags. The service rejects/repairs malformed output before persistence. Ingredient names are canonicalized against the `Ingredient` table (fuzzy match → existing id, or create new).

### Cost controls
- Token usage logged per generation → feeds free-tier limit tuning (see spec §6.1)
- Prompt caching for the stable parts of prompts (system instructions, schema)
- Per-user/household rate limiting enforced before calling Claude

---

## 6. Data Access & Row Level Security

RLS is the backbone that makes direct client→Supabase access safe, and it must encode the **household membership model** precisely.

### Core policy principle
A user may access a row only if they are a member of the household that owns it.

```sql
-- Conceptual: pantry_items visible only to members of the owning household
create policy "members can read pantry"
on pantry_items for select
using (
  household_id in (
    select household_id from household_members
    where user_id = auth.uid()
  )
);
```

### Policy matrix (v1)
| Table | Read | Write |
|---|---|---|
| `households` | members | owner |
| `household_members` | members | owner (invites/roles) |
| `users` (self) | self | self |
| `meal_plans` | members | members |
| `meal_plan_days` / `meals` | members | members |
| `pantry_items` | members | members |
| `shopping_lists` / items | members | members |
| `recipes` (shared) | all authenticated | — (created by AI Service) |
| `recipes` (user-owned) | owning user / household | owning user |

> **Note:** v1 ships single-household-per-user, but RLS is written against the membership model from day one so multi-household (v2) needs no policy rewrite — just lift the app-level "one household" guard.

The **AI Service** uses a privileged Supabase connection (service role) but performs its **own** membership authorization in code (Section 4), so it never relies on RLS as its only guard.

---

## 7. Pricing & USDA Data Pipeline

### Baseline pricing
- A scheduled **USDA Sync Job** refreshes `Ingredient.usda_price_per_unit` on a cadence (TBD once update frequency is confirmed — see spec open questions).
- Stored per ingredient with `usda_unit` and `last_usda_sync`.

### Localization
- **User calibration anchors** (per household): a small set of confirmed local prices (milk, eggs, bread, etc.) → compute a regional adjustment factor applied to the USDA baseline.
- **AI-assisted estimate** (optional, on demand): `POST /v1/pricing/estimate` asks Claude for region/store-aware prices when baseline confidence is low.

### Budget reconciliation
When building a shopping list:
1. Compute required quantities from the meal plan.
2. Subtract pantry quantities.
3. Price remaining items (calibrated USDA baseline; AI estimate as fallback).
4. Sum → `estimated_total`; compare to `MealPlan.budget`; warn if over.

Target accuracy: **within 10–15%** of actual (per spec).

---

## 8. API Surface

Two logical APIs the clients consume:

### A. Supabase (auto-generated + RLS)
Standard PostgREST/Supabase client calls for CRUD. No custom code; contracts come from generated DB types shared via `@mise/shared`.

### B. AI Service (explicit REST)
Versioned under `/v1`. Request/response schemas defined once (Zod on the TS side, Pydantic on the Python side) and kept in sync via the shared contract definitions. All endpoints require a valid Supabase JWT.

**Contract sync strategy:** the source of truth for AI Service schemas is the Pydantic models; we generate/mirror TypeScript types in `@mise/shared` so clients are type-safe against the AI Service.

---

## 9. Core Loop: End-to-End Request Flows

### Flow 1 — Generate a meal plan
```
Client → AI Service: POST /v1/meal-plans/generate { household_id, start, end, prefs }
AI Service: verify JWT, check membership
AI Service → DB: read pantry, dietary prefs, budget
AI Service: create job (queued) → return 202 { job_id }
AI Service → Claude: prompt (context + JSON schema)
Claude → AI Service: structured plan
AI Service: validate, canonicalize ingredients, persist plan + recipes
AI Service → DB: job status = done
DB Realtime → Client: job done → client fetches the new plan
```

### Flow 2 — Override a single meal
```
Client → AI Service: POST /v1/recipes/generate { meal_id, constraints }
... (same generate→validate→persist pattern, scoped to one meal slot)
Client → DB: update meal.recipe_id (direct, RLS-guarded)
```

### Flow 3 — Build shopping list from plan
```
Client → DB: read meal plan + recipes (direct)
Client → DB: read pantry (direct)
Client computes required − pantry  (or AI Service does it for pricing accuracy)
Client → AI Service: POST /v1/pricing/estimate { items, region, store }   (optional)
Client → DB: insert shopping_list + items with estimated prices
Client compares total vs budget → UI warning if over
```

### Flow 4 — Cook a meal (pantry depletion)
```
Client → DB: update meal.cooked_at (direct)
If depletion mode = auto:
  for each recipe ingredient:
     deduct = qty × (meal.servings / recipe.default_servings)
     if partial-use likely → prompt user to confirm actual amount
  Client → DB: update pantry_items quantities (direct)
If manual: user edits pantry directly later
```

---

## 10. Repository Structure

A **monorepo** (pnpm workspaces + Turborepo) keeps shared types and contracts coherent across web, mobile, and the AI service.

```
Mise/
├── docs/
│   ├── PRODUCT_SPEC.md
│   └── ARCHITECTURE.md
├── apps/
│   ├── web/                 # Next.js
│   ├── mobile/              # Expo / React Native
│   └── ai-service/          # FastAPI (Python; own venv/poetry)
├── packages/
│   └── shared/              # @mise/shared — TS types, Zod schemas, constants
├── supabase/
│   ├── migrations/          # SQL schema + RLS policies
│   └── seed/                # seed data (ingredients, etc.)
├── infra/                   # IaC / deployment config (later)
├── package.json             # workspace root
├── pnpm-workspace.yaml
└── turbo.json
```

> The Python `ai-service` lives in the monorepo for cohesion but manages its own dependencies (Poetry/uv) and is built/deployed independently of the JS apps.

---

## 11. Environments & Deployment

| Component | Hosting (proposed) | Notes |
|---|---|---|
| Web (Next.js) | Vercel | Natural fit; preview deploys per PR |
| Mobile (Expo) | EAS Build + app stores | OTA updates via Expo |
| AI Service (FastAPI) | Fly.io / Render / Railway | Container; scales independently; holds Claude API key |
| Database/Auth/Storage | Supabase (managed) | Separate projects per environment |
| USDA Sync Job | Scheduled (cron on host / GitHub Actions) | Writes to Supabase |

**Environments:** `local` → `staging` → `production`, each with its own Supabase project and AI Service deployment. Secrets (Claude key, Supabase service role) live only server-side in the AI Service env.

---

## 12. Cross-Cutting Concerns

- **Secrets:** Claude API key and Supabase service-role key live **only** in the AI Service environment — never shipped to clients.
- **Validation:** Zod (TS) + Pydantic (Python) at every boundary; LLM output validated/repaired before persistence.
- **Rate limiting & abuse:** per-user/household limits on generation endpoints (also enforces free-tier caps).
- **Observability:** structured logs + request tracing on the AI Service; token-usage metrics per generation.
- **Offline (mobile):** shopping list checkout benefits from offline support — cache the list locally and sync checkbox state on reconnect (flagged in spec open questions; likely v1.x).
- **Error handling:** generation failures surface as job `status: failed` with a user-friendly retry path.
- **Privacy:** anonymized data-insights monetization (spec §6.4) requires explicit opt-in; keep PII isolated and exportable/deletable.

---

## 13. Architectural Decisions & Trade-offs

| Decision | Choice | Rationale | Trade-off |
|---|---|---|---|
| Backend shape | Supabase + thin FastAPI AI service | Fast to build; CRUD is free; AI logic isolated & testable | Two server surfaces to operate |
| Client → CRUD | Direct to Supabase (RLS) | Less code, lower latency | Security depends on correct RLS — must be rigorous |
| AI provider | Claude, abstracted | Strong structured output; swappable | Vendor cost scales with usage |
| Generation | Async job + Realtime | Avoids timeouts; enables retry/streaming | More moving parts than a blocking call |
| Multi-household | RLS built for it now, gated in app for v1 | No migration later | Slightly more policy complexity up front |
| Monorepo | pnpm + Turborepo | Shared types across web/mobile/AI | Python app is a slight outlier in a JS-centric monorepo |
| Pricing | USDA baseline + calibration + AI fallback | Hits 10–15% target without store APIs | Not exact; real-time pricing deferred to v2 |

---

## Next Steps (post-architecture)

1. **Database implementation** — write `supabase/migrations` for the schema + RLS policies; seed the `Ingredient` table.
2. **AI layer design** — prompt + structured-output schema for meal plan generation; cost benchmark.
3. **Repo scaffolding** — stand up the monorepo skeleton (apps + packages + supabase).
4. **Build v1 core loop** — auth → household → generate → shopping list → pantry → cook.
