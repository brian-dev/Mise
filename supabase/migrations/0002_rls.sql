-- Mise — Row Level Security
-- See docs/ARCHITECTURE.md §6
--
-- Model: a user may access a row only if they are a member of the household
-- that owns it. Policies are written against the membership model from day one
-- so multi-household (v2) needs no rewrite — v1 just gates "one household" in
-- the app layer.
--
-- The AI Service connects with the service_role key, which BYPASSES RLS; it
-- performs its own membership authorization in code (ARCHITECTURE §4).

-- ---------------------------------------------------------------------------
-- Membership helper (SECURITY DEFINER to avoid recursive RLS on the lookup)
-- ---------------------------------------------------------------------------
create or replace function is_household_member(hid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from household_members
    where household_id = hid
      and user_id = auth.uid()
  );
$$;

create or replace function is_household_owner(hid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from household_members
    where household_id = hid
      and user_id = auth.uid()
      and role = 'owner'
  );
$$;

-- ---------------------------------------------------------------------------
-- Enable RLS on all application tables
-- ---------------------------------------------------------------------------
alter table users               enable row level security;
alter table households          enable row level security;
alter table household_members   enable row level security;
alter table ingredients         enable row level security;
alter table recipes             enable row level security;
alter table recipe_ingredients  enable row level security;
alter table meal_plans          enable row level security;
alter table meal_plan_days      enable row level security;
alter table meals               enable row level security;
alter table pantry_items        enable row level security;
alter table shopping_lists      enable row level security;
alter table shopping_list_items enable row level security;
alter table generation_jobs     enable row level security;

-- ---------------------------------------------------------------------------
-- users: a user sees and edits only their own profile row
-- ---------------------------------------------------------------------------
create policy users_select_self on users
  for select using (id = auth.uid());
create policy users_insert_self on users
  for insert with check (id = auth.uid());
create policy users_update_self on users
  for update using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------------------------
-- households: members read; owners write
-- ---------------------------------------------------------------------------
create policy households_select_member on households
  for select using (is_household_member(id));
create policy households_update_owner on households
  for update using (is_household_owner(id)) with check (is_household_owner(id));
create policy households_delete_owner on households
  for delete using (is_household_owner(id));
-- Insert: any authenticated user may create a household (they become owner via
-- household_members insert in the same transaction, app-side).
create policy households_insert_authenticated on households
  for insert with check (auth.uid() is not null);

-- ---------------------------------------------------------------------------
-- household_members
--   read: members of the same household
--   write: owners (invites/role changes); plus self-insert for bootstrapping
-- ---------------------------------------------------------------------------
create policy household_members_select on household_members
  for select using (is_household_member(household_id));
-- Bootstrap: a user may insert their OWN membership (e.g., creating a household
-- and adding themselves as owner). Owner-driven invites also satisfy this when
-- performed by the owner adding others.
create policy household_members_insert on household_members
  for insert with check (
    user_id = auth.uid() or is_household_owner(household_id)
  );
create policy household_members_update_owner on household_members
  for update using (is_household_owner(household_id))
  with check (is_household_owner(household_id));
create policy household_members_delete on household_members
  for delete using (
    is_household_owner(household_id) or user_id = auth.uid()  -- owners remove; members can leave
  );

-- ---------------------------------------------------------------------------
-- ingredients: shared catalog, readable by all authenticated users.
-- Writes are done by the AI Service (service_role, bypasses RLS).
-- ---------------------------------------------------------------------------
create policy ingredients_select_authenticated on ingredients
  for select using (auth.uid() is not null);

-- ---------------------------------------------------------------------------
-- recipes:
--   shared pool (created_by_user_id is null) readable by all authenticated
--   user-owned recipes readable/writable by the owning user
-- ---------------------------------------------------------------------------
create policy recipes_select on recipes
  for select using (
    created_by_user_id is null or created_by_user_id = auth.uid()
  );
create policy recipes_insert_self on recipes
  for insert with check (created_by_user_id = auth.uid());
create policy recipes_update_owner on recipes
  for update using (created_by_user_id = auth.uid())
  with check (created_by_user_id = auth.uid());
create policy recipes_delete_owner on recipes
  for delete using (created_by_user_id = auth.uid());

-- recipe_ingredients: visible/writable when the parent recipe is.
create policy recipe_ingredients_select on recipe_ingredients
  for select using (
    exists (
      select 1 from recipes r
      where r.id = recipe_id
        and (r.created_by_user_id is null or r.created_by_user_id = auth.uid())
    )
  );
create policy recipe_ingredients_write on recipe_ingredients
  for all using (
    exists (
      select 1 from recipes r
      where r.id = recipe_id and r.created_by_user_id = auth.uid()
    )
  ) with check (
    exists (
      select 1 from recipes r
      where r.id = recipe_id and r.created_by_user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- meal_plans: members of the owning household (read + write)
-- ---------------------------------------------------------------------------
create policy meal_plans_all_member on meal_plans
  for all using (is_household_member(household_id))
  with check (is_household_member(household_id));

-- meal_plan_days: gated through the parent plan's household
create policy meal_plan_days_all_member on meal_plan_days
  for all using (
    exists (
      select 1 from meal_plans mp
      where mp.id = meal_plan_id and is_household_member(mp.household_id)
    )
  ) with check (
    exists (
      select 1 from meal_plans mp
      where mp.id = meal_plan_id and is_household_member(mp.household_id)
    )
  );

-- meals: gated through day -> plan -> household
create policy meals_all_member on meals
  for all using (
    exists (
      select 1
      from meal_plan_days d
      join meal_plans mp on mp.id = d.meal_plan_id
      where d.id = meal_plan_day_id and is_household_member(mp.household_id)
    )
  ) with check (
    exists (
      select 1
      from meal_plan_days d
      join meal_plans mp on mp.id = d.meal_plan_id
      where d.id = meal_plan_day_id and is_household_member(mp.household_id)
    )
  );

-- ---------------------------------------------------------------------------
-- pantry_items: members of the owning household
-- ---------------------------------------------------------------------------
create policy pantry_items_all_member on pantry_items
  for all using (is_household_member(household_id))
  with check (is_household_member(household_id));

-- ---------------------------------------------------------------------------
-- shopping_lists: gated through the parent plan's household
-- ---------------------------------------------------------------------------
create policy shopping_lists_all_member on shopping_lists
  for all using (
    exists (
      select 1 from meal_plans mp
      where mp.id = meal_plan_id and is_household_member(mp.household_id)
    )
  ) with check (
    exists (
      select 1 from meal_plans mp
      where mp.id = meal_plan_id and is_household_member(mp.household_id)
    )
  );

-- shopping_list_items: gated through list -> plan -> household
create policy shopping_list_items_all_member on shopping_list_items
  for all using (
    exists (
      select 1
      from shopping_lists sl
      join meal_plans mp on mp.id = sl.meal_plan_id
      where sl.id = shopping_list_id and is_household_member(mp.household_id)
    )
  ) with check (
    exists (
      select 1
      from shopping_lists sl
      join meal_plans mp on mp.id = sl.meal_plan_id
      where sl.id = shopping_list_id and is_household_member(mp.household_id)
    )
  );

-- ---------------------------------------------------------------------------
-- generation_jobs: members of the owning household can read; the AI Service
-- (service_role) creates/updates them. Clients read job status via Realtime.
-- ---------------------------------------------------------------------------
create policy generation_jobs_select_member on generation_jobs
  for select using (is_household_member(household_id));
