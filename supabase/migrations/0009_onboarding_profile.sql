-- Mise — Onboarding profile, consent ledger, and analytics events
--
-- Captures a household "how you cook" snapshot at sign-up so plan generation
-- starts from smart defaults (UX onboarding wizard), plus the data-asset
-- groundwork: an auditable consent ledger and a structured analytics-events
-- stream. See docs/UX_DESIGN.md (onboarding) and CLAUDE.md.

-- ---------------------------------------------------------------------------
-- Household profile (the onboarding snapshot). region/store_preference already
-- exist on households; these are the rest. All optional — null/empty = unset.
-- ---------------------------------------------------------------------------
alter table households
  add column household_size       int,
  add column weekly_budget        numeric(10,2),
  add column preferred_cuisines   text[] not null default '{}',
  add column preferred_meal_types text[] not null default '{}',  -- breakfast|lunch|dinner|snack
  add column cooking_time         text,                          -- quick|standard|elaborate
  add column dietary_flags        text[] not null default '{}',
  add column avoid_text           text,
  add column onboarding_completed_at timestamptz;

-- ---------------------------------------------------------------------------
-- Consent ledger — append-only. Each grant/revoke inserts a new row; the
-- "current" state for a (user, kind) is the most recent row. Keeps a full,
-- auditable history (what was granted, which policy version, when).
--   kind: personalization | analytics | data_sharing | marketing
-- ---------------------------------------------------------------------------
create table user_consents (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references users (id) on delete cascade,
  kind       text not null,
  granted    boolean not null,
  version    text not null,                       -- consent-copy version, e.g. '2026-06-12'
  created_at timestamptz not null default now()
);

create index user_consents_user_idx on user_consents (user_id, kind, created_at desc);

-- ---------------------------------------------------------------------------
-- Analytics events — structured, append-only behavioral stream. PII stays in
-- users/households; this references them by id and carries typed properties.
--   event_type: signup | onboarding_completed | plan_generated | meal_cooked |
--               shopping_list_purchased | ...
-- ---------------------------------------------------------------------------
create table analytics_events (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references users (id) on delete set null,
  household_id uuid references households (id) on delete set null,
  event_type   text not null,
  properties   jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);

create index analytics_events_type_created_idx on analytics_events (event_type, created_at desc);
create index analytics_events_user_idx          on analytics_events (user_id);

-- ---------------------------------------------------------------------------
-- RLS (ARCHITECTURE §6). The AI service uses the service_role key and bypasses
-- RLS, doing its own authz; these policies gate any direct client access.
-- ---------------------------------------------------------------------------
alter table user_consents   enable row level security;
alter table analytics_events enable row level security;

-- A user may read their own consent history. Writes go through the AI service
-- (service_role), so no client insert/update policy is granted.
create policy user_consents_select_self on user_consents
  for select using (user_id = auth.uid());

-- analytics_events: no client policies — RLS-enabled with none means only the
-- service_role (which bypasses RLS) can read or write. Locked down by default.
