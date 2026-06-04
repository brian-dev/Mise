// AI generation contract types — the structured output Claude emits
// (docs/AI_LAYER.md §4). The AI service emits these shapes (ingredient *names*,
// not ids); the server canonicalizes names to ingredient ids on persistence.

import type { MealType, Unit } from "./enums.js";

export interface GeneratedIngredient {
  name: string;
  category?: string;
  quantity: number;
  unit: Unit;
  is_optional?: boolean;
}

export interface GeneratedRecipe {
  title: string;
  description?: string;
  cuisine_tags: string[];
  prep_time?: number;
  cook_time?: number;
  default_servings: number;
  instructions: string;
  ingredients: GeneratedIngredient[];
}

export interface GeneratedMeal {
  meal_type: MealType;
  servings?: number;
  recipe: GeneratedRecipe;
}

export interface GeneratedDay {
  /** ISO date (YYYY-MM-DD). */
  date: string;
  meals: GeneratedMeal[];
}

/** Output of the `emit_meal_plan` tool. */
export interface GeneratedMealPlan {
  days: GeneratedDay[];
}
