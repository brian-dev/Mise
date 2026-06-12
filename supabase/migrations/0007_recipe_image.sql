-- Mise — Recipe images
--
-- Recipes carry a representative (not exact) photo for the plan/recipe UI,
-- sourced from a free stock provider (Pexels) keyed on the recipe title, then
-- cuisine, then none. Stored once so we don't re-fetch on every view; null until
-- first resolved. See docs/UX_DESIGN.md §8 (Theming & Recipe Images).

alter table recipes add column image_url text;
