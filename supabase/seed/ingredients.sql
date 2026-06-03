-- Mise — Ingredient seed data
--
-- A starter catalog of common grocery ingredients with placeholder USDA-style
-- baseline prices. Real pricing will be refreshed by the USDA Sync Job
-- (see ARCHITECTURE §7); these values are illustrative starting points so the
-- shopping-list/budget flow is exercisable in development.
--
-- Prices are per the listed usda_unit, in USD. last_usda_sync left null to
-- signal "not yet synced from authoritative source".

insert into ingredients (name, category, usda_price_per_unit, usda_unit) values
  -- Produce
  ('Yellow Onion',        'produce',       0.90, 'lb'),
  ('Garlic',              'produce',       4.00, 'lb'),
  ('Roma Tomato',         'produce',       1.80, 'lb'),
  ('Carrot',              'produce',       1.20, 'lb'),
  ('Russet Potato',       'produce',       0.95, 'lb'),
  ('Broccoli',            'produce',       2.20, 'lb'),
  ('Spinach',             'produce',       3.50, 'lb'),
  ('Bell Pepper',         'produce',       1.50, 'each'),
  ('Lemon',               'produce',       0.70, 'each'),
  ('Lime',                'produce',       0.50, 'each'),
  ('Avocado',             'produce',       1.25, 'each'),
  ('Banana',              'produce',       0.60, 'lb'),
  -- Dairy & eggs
  ('Whole Milk',          'dairy',         3.80, 'gallon'),
  ('Large Eggs',          'dairy',         3.20, 'dozen'),
  ('Unsalted Butter',     'dairy',         4.50, 'lb'),
  ('Cheddar Cheese',      'dairy',         5.50, 'lb'),
  ('Greek Yogurt',        'dairy',         5.00, 'quart'),
  ('Parmesan Cheese',     'dairy',        12.00, 'lb'),
  -- Meat & protein
  ('Chicken Breast',      'meat',          3.90, 'lb'),
  ('Chicken Thigh',       'meat',          2.80, 'lb'),
  ('Ground Beef (80/20)', 'meat',          5.20, 'lb'),
  ('Pork Chop',           'meat',          4.10, 'lb'),
  ('Salmon Fillet',       'meat',         11.00, 'lb'),
  ('Bacon',               'meat',          6.50, 'lb'),
  ('Black Beans (canned)','protein',       1.10, 'can'),
  ('Tofu (firm)',         'protein',       2.50, 'block'),
  -- Pantry staples
  ('All-Purpose Flour',   'pantry staple', 0.55, 'lb'),
  ('Granulated Sugar',    'pantry staple', 0.70, 'lb'),
  ('White Rice',          'pantry staple', 1.00, 'lb'),
  ('Pasta (dry)',         'pantry staple', 1.30, 'lb'),
  ('Olive Oil',           'pantry staple', 9.00, 'liter'),
  ('Canola Oil',          'pantry staple', 4.00, 'liter'),
  ('Salt',                'pantry staple', 0.60, 'lb'),
  ('Black Pepper',        'pantry staple',12.00, 'lb'),
  ('Soy Sauce',           'pantry staple', 3.50, 'bottle'),
  ('Canned Tomatoes',     'pantry staple', 1.30, 'can'),
  ('Chicken Stock',       'pantry staple', 2.50, 'quart'),
  ('Honey',               'pantry staple', 7.00, 'lb'),
  ('Peanut Butter',       'pantry staple', 4.50, 'jar'),
  -- Bakery & grains
  ('Sandwich Bread',      'bakery',        2.80, 'loaf'),
  ('Tortillas (flour)',   'bakery',        3.00, 'pack'),
  ('Rolled Oats',         'pantry staple', 2.20, 'lb')
on conflict (name) do nothing;
