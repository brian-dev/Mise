-- Mise — make generation_jobs.requested_by nullable
--
-- v1 runs pre-auth (no users yet); the synchronous-to-async generation flow
-- needs to create a job without a requesting user. Auth (ARCHITECTURE §4) will
-- populate requested_by once it lands. The FK + on-delete-cascade are retained.

alter table generation_jobs
  alter column requested_by drop not null;
