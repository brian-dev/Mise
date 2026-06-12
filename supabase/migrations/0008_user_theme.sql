-- Mise — Per-user theme preference
--
-- The selected UI theme (warm/fresh/dark) persists to the user's profile so it
-- follows them across devices. localStorage remains the instant, pre-auth cache;
-- this is the source of truth once signed in. Null = no choice saved yet.

alter table users add column theme text;
