-- Mise — expose generation_jobs over Supabase Realtime
--
-- Clients subscribe to their generation job row to learn when a meal plan is
-- ready (ARCHITECTURE §5), instead of polling. RLS already restricts SELECT to
-- household members (generation_jobs_select_member in 0002), and Realtime honors
-- that policy — a user only receives changes to jobs in their household.
--
-- REPLICA IDENTITY FULL so the change payload carries the columns RLS needs
-- (household_id) on UPDATE, not just the primary key.

alter table generation_jobs replica identity full;
alter publication supabase_realtime add table generation_jobs;
