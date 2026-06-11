-- Mise — Ingredient shelf life (for pantry "use soon" expiry estimation)
--
-- The dashboard estimates when a pantry item should be used by from the date it
-- was added plus a typical shelf life. Accuracy is best-effort: we key off the
-- ingredient's free-form `category` (set by the AI / seed catalog) against a
-- small table of category averages distilled from the USDA FoodKeeper data
-- (refrigerated/pantry storage, in days). An optional per-ingredient override
-- lets us refine specific items later without touching the category defaults.

create table category_shelf_life (
  category   text primary key,
  days       int  not null check (days > 0)
);

comment on table category_shelf_life is
  'Typical shelf life (days) by ingredient category, from USDA FoodKeeper averages.';

-- Per-ingredient override (null = fall back to the category default).
alter table ingredients add column shelf_life_days int;

-- Category averages. Conservative refrigerated/pantry storage estimates.
insert into category_shelf_life (category, days) values
  ('produce',        7),
  ('vegetable',      7),
  ('vegetables',     7),
  ('fruit',          7),
  ('herbs',          5),
  ('dairy',          14),
  ('eggs',           21),
  ('meat',           4),
  ('protein',        4),
  ('poultry',        2),
  ('seafood',        2),
  ('fish',           2),
  ('bakery',         5),
  ('bread',          7),
  ('deli',           5),
  ('leftovers',      4),
  ('condiment',      180),
  ('condiments',     180),
  ('sauce',          120),
  ('frozen',         180),
  ('canned',         730),
  ('grains',         365),
  ('grain',          365),
  ('spice',          730),
  ('spices',         730),
  ('baking',         365),
  ('oil',            365),
  ('pantry staple',  365),
  ('pantry',         365),
  ('beverage',       120);
