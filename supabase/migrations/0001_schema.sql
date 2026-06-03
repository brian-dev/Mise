-- Mise — Initial schema
-- See docs/PRODUCT_SPEC.md §4 and docs/ARCHITECTURE.md §6
--
-- Conventions:
--   * UUID primary keys (gen_random_uuid)
--   * snake_case identifiers
--   * timestamptz for all timestamps, default now()
--   * enums via Postgres enum types
--   * updated_at maintained by trigger

create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "pg_trgm";    -- fuzzy ingredient-name matching

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type household_role        as enum ('owner', 'member');
create type pantry_depletion_mode as enum ('auto', 'manual');
create type meal_plan_status      as enum ('draft', 'active', 'closed');
create type meal_type             as enum ('breakfast', 'lunch', 'dinner', 'snack');
create type shopping_list_status  as enum ('draft', 'finalized', 'purchased');
create type shopping_item_source  as enum ('recipe', 'manual');
create type generation_job_status as enum ('queued', 'running', 'done', 'failed');

-- ---------------------------------------------------------------------------
-- updated_at trigger helper
-- ---------------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- users  (profile rows; auth lives in auth.users)
--   id mirrors auth.users.id
-- ---------------------------------------------------------------------------
create table users (
  id                  uuid primary key references auth.users (id) on delete cascade,
  email               text not null,
  name                text,
  dietary_preferences jsonb not null default '{}'::jsonb,  -- structured flags + freeform dislikes
  active_household_id uuid,                                  -- FK added after households exists
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- households  (a location: "Home", "Jake's College Apt")
-- ---------------------------------------------------------------------------
create table households (
  id                    uuid primary key default gen_random_uuid(),
  name                  text not null,
  store_preference      text,
  region                text,                                       -- for USDA pricing lookup
  price_calibration     jsonb not null default '{}'::jsonb,         -- anchor item prices
  pantry_depletion_mode pantry_depletion_mode not null default 'auto',
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

alter table users
  add constraint users_active_household_fk
  foreign key (active_household_id) references households (id) on delete set null;

-- ---------------------------------------------------------------------------
-- household_members  (membership + role)
-- ---------------------------------------------------------------------------
create table household_members (
  id           uuid primary key default gen_random_uuid(),
  household_id uuid not null references households (id) on delete cascade,
  user_id      uuid not null references users (id) on delete cascade,
  role         household_role not null default 'member',
  created_at   timestamptz not null default now(),
  unique (household_id, user_id)
);

create index household_members_user_idx      on household_members (user_id);
create index household_members_household_idx on household_members (household_id);

-- ---------------------------------------------------------------------------
-- ingredients  (canonical catalog; baseline pricing from USDA)
-- ---------------------------------------------------------------------------
create table ingredients (
  id                  uuid primary key default gen_random_uuid(),
  name                text not null unique,        -- canonical name
  category            text,                         -- produce | dairy | meat | pantry staple | ...
  usda_price_per_unit numeric(10,4),
  usda_unit           text,
  last_usda_sync      timestamptz,
  created_at          timestamptz not null default now()
);

create index ingredients_name_trgm_idx on ingredients using gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- recipes  (shared pool when created_by_user_id is null)
-- ---------------------------------------------------------------------------
create table recipes (
  id                  uuid primary key default gen_random_uuid(),
  created_by_user_id  uuid references users (id) on delete set null,  -- null = shared pool
  title               text not null,
  description         text,
  cuisine_tags        text[] not null default '{}',
  prep_time           int,                          -- minutes
  cook_time           int,                          -- minutes
  default_servings    int not null default 2,
  instructions        text,
  is_ai_generated     boolean not null default true,
  source_prompt       text,                         -- prompt used to generate, for iteration
  created_at          timestamptz not null default now()
);

create index recipes_owner_idx on recipes (created_by_user_id);

-- ---------------------------------------------------------------------------
-- recipe_ingredients
-- ---------------------------------------------------------------------------
create table recipe_ingredients (
  id            uuid primary key default gen_random_uuid(),
  recipe_id     uuid not null references recipes (id) on delete cascade,
  ingredient_id uuid not null references ingredients (id) on delete restrict,
  quantity      numeric(10,3) not null,
  unit          text not null,
  is_optional   boolean not null default false
);

create index recipe_ingredients_recipe_idx     on recipe_ingredients (recipe_id);
create index recipe_ingredients_ingredient_idx on recipe_ingredients (ingredient_id);

-- ---------------------------------------------------------------------------
-- meal_plans  (one active plan per household enforced via partial unique idx)
-- ---------------------------------------------------------------------------
create table meal_plans (
  id           uuid primary key default gen_random_uuid(),
  household_id uuid not null references households (id) on delete cascade,
  status       meal_plan_status not null default 'draft',
  start_date   date not null,
  end_date     date not null,
  budget       numeric(10,2),
  created_at   timestamptz not null default now(),
  closed_at    timestamptz,
  check (end_date >= start_date)
);

create index meal_plans_household_idx on meal_plans (household_id);

-- At most one active plan per household.
create unique index meal_plans_one_active_per_household
  on meal_plans (household_id)
  where status = 'active';

-- ---------------------------------------------------------------------------
-- meal_plan_days
-- ---------------------------------------------------------------------------
create table meal_plan_days (
  id           uuid primary key default gen_random_uuid(),
  meal_plan_id uuid not null references meal_plans (id) on delete cascade,
  date         date not null,
  unique (meal_plan_id, date)
);

create index meal_plan_days_plan_idx on meal_plan_days (meal_plan_id);

-- ---------------------------------------------------------------------------
-- meals
-- ---------------------------------------------------------------------------
create table meals (
  id               uuid primary key default gen_random_uuid(),
  meal_plan_day_id uuid not null references meal_plan_days (id) on delete cascade,
  meal_type        meal_type not null,
  recipe_id        uuid references recipes (id) on delete set null,
  servings         int not null default 2,
  cooked_at        timestamptz
);

create index meals_day_idx    on meals (meal_plan_day_id);
create index meals_recipe_idx on meals (recipe_id);

-- ---------------------------------------------------------------------------
-- pantry_items
-- ---------------------------------------------------------------------------
create table pantry_items (
  id            uuid primary key default gen_random_uuid(),
  household_id  uuid not null references households (id) on delete cascade,
  ingredient_id uuid not null references ingredients (id) on delete restrict,
  quantity      numeric(10,3) not null default 0,
  unit          text not null,
  added_at      timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (household_id, ingredient_id, unit)
);

create index pantry_items_household_idx on pantry_items (household_id);

-- ---------------------------------------------------------------------------
-- shopping_lists
-- ---------------------------------------------------------------------------
create table shopping_lists (
  id               uuid primary key default gen_random_uuid(),
  meal_plan_id     uuid not null references meal_plans (id) on delete cascade,
  store_preference text,
  estimated_total  numeric(10,2),
  status           shopping_list_status not null default 'draft',
  created_at       timestamptz not null default now()
);

create index shopping_lists_plan_idx on shopping_lists (meal_plan_id);

-- ---------------------------------------------------------------------------
-- shopping_list_items
-- ---------------------------------------------------------------------------
create table shopping_list_items (
  id               uuid primary key default gen_random_uuid(),
  shopping_list_id uuid not null references shopping_lists (id) on delete cascade,
  ingredient_id    uuid not null references ingredients (id) on delete restrict,
  quantity_needed  numeric(10,3) not null,           -- after pantry subtraction
  unit             text not null,
  estimated_price  numeric(10,2),
  is_checked       boolean not null default false,
  source           shopping_item_source not null default 'recipe'
);

create index shopping_list_items_list_idx on shopping_list_items (shopping_list_id);

-- ---------------------------------------------------------------------------
-- generation_jobs  (async AI generation tracking; see ARCHITECTURE §5)
-- ---------------------------------------------------------------------------
create table generation_jobs (
  id           uuid primary key default gen_random_uuid(),
  household_id uuid not null references households (id) on delete cascade,
  requested_by uuid not null references users (id) on delete cascade,
  kind         text not null,                         -- 'meal_plan' | 'recipe' | 'recipe_iterate'
  status       generation_job_status not null default 'queued',
  request      jsonb not null default '{}'::jsonb,
  result       jsonb,                                  -- e.g., { meal_plan_id } on success
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index generation_jobs_household_idx on generation_jobs (household_id);
create index generation_jobs_status_idx    on generation_jobs (status);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
create trigger trg_users_updated            before update on users            for each row execute function set_updated_at();
create trigger trg_households_updated        before update on households        for each row execute function set_updated_at();
create trigger trg_pantry_items_updated      before update on pantry_items      for each row execute function set_updated_at();
create trigger trg_generation_jobs_updated   before update on generation_jobs   for each row execute function set_updated_at();
