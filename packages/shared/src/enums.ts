// Canonical enums — mirror supabase/migrations/0001_schema.sql.
// Keep this file in lockstep with the Postgres enum types and the AI tool
// schema (docs/AI_LAYER.md §4). One source of truth for web, mobile, and the
// typed Supabase clients.

export const HOUSEHOLD_ROLES = ["owner", "member"] as const;
export type HouseholdRole = (typeof HOUSEHOLD_ROLES)[number];

export const PANTRY_DEPLETION_MODES = ["auto", "manual"] as const;
export type PantryDepletionMode = (typeof PANTRY_DEPLETION_MODES)[number];

export const MEAL_PLAN_STATUSES = ["draft", "active", "closed"] as const;
export type MealPlanStatus = (typeof MEAL_PLAN_STATUSES)[number];

export const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"] as const;
export type MealType = (typeof MEAL_TYPES)[number];

export const SHOPPING_LIST_STATUSES = ["draft", "finalized", "purchased"] as const;
export type ShoppingListStatus = (typeof SHOPPING_LIST_STATUSES)[number];

export const SHOPPING_ITEM_SOURCES = ["recipe", "manual"] as const;
export type ShoppingItemSource = (typeof SHOPPING_ITEM_SOURCES)[number];

export const GENERATION_JOB_STATUSES = ["queued", "running", "done", "failed"] as const;
export type GenerationJobStatus = (typeof GENERATION_JOB_STATUSES)[number];

// Controlled unit vocabulary for recipe/pantry quantities (docs/AI_LAYER.md §D4).
// Constraining units at the boundary keeps depletion math and pantry de-dup sane.
export const UNITS = [
  // mass
  "g", "kg", "oz", "lb",
  // volume
  "ml", "l", "tsp", "tbsp", "cup", "fl_oz",
  // count
  "unit", "clove", "slice", "can", "bunch", "pinch",
] as const;
export type Unit = (typeof UNITS)[number];
