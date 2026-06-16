-- Mise — Per-user recipe favorites + notes
--
-- Both are personal to a user (not the household): a favorite flag and a free-text
-- note, each keyed by (user, recipe). Surfaced on the recipe detail screen.

create table recipe_favorites (
  user_id    uuid not null references users (id) on delete cascade,
  recipe_id  uuid not null references recipes (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, recipe_id)
);

create index recipe_favorites_user_idx on recipe_favorites (user_id, created_at desc);

create table recipe_notes (
  user_id    uuid not null references users (id) on delete cascade,
  recipe_id  uuid not null references recipes (id) on delete cascade,
  note       text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, recipe_id)
);

-- RLS: a user sees/edits only their own favorites + notes. The AI service uses
-- the service_role key (bypasses RLS) and gates on current_user in code.
alter table recipe_favorites enable row level security;
alter table recipe_notes     enable row level security;

create policy recipe_favorites_self on recipe_favorites
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy recipe_notes_self on recipe_notes
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
