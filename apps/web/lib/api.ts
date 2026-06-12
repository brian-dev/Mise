// Thin client for the Mise AI service (local dev harness).
// Base URL overridable via NEXT_PUBLIC_API_URL.

import type { MealType } from "@mise/shared";

import { supabase } from "./supabase";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  // Attach the Supabase access token so the AI service can authorize the caller.
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface Household {
  id: string;
  name: string;
}

export interface PantryItem {
  name: string;
  quantity: string;
  unit: string;
}

export interface PlanMeal {
  meal_id: string;
  meal_type: MealType;
  servings: number;
  cooked_at: string | null;
  recipe_id: string;
  recipe_title: string;
}

export interface RecipeIngredient {
  name: string;
  quantity: string;
  unit: string;
  is_optional: boolean;
}

export interface RecipeDetail {
  recipe_id: string;
  title: string;
  description: string | null;
  cuisine_tags: string[];
  prep_time: number | null;
  cook_time: number | null;
  default_servings: number;
  instructions: string | null;
  image_url: string | null;
  ingredients: RecipeIngredient[];
}

export interface PlanDay {
  date: string;
  meals: PlanMeal[];
}

export interface MealPlanDetail {
  meal_plan_id: string;
  status: string;
  start_date: string;
  end_date: string;
  budget: string | null;
  days: PlanDay[];
}

export interface JobAccepted {
  job_id: string;
  status: string;
}

export interface JobStatus {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  result: { meal_plan_id?: string } | null;
  error: string | null;
}

export interface ShoppingSummary {
  shopping_list_id: string;
  estimated_total: string;
  budget: string | null;
  over_budget: boolean;
  items_total: number;
  items_priced: number;
  items_unpriced: number;
}

export interface ShoppingItem {
  name: string;
  quantity_needed: string;
  unit: string;
  estimated_price: string | null;
  is_checked: boolean;
  source: string;
}

export interface ShoppingListDetail {
  shopping_list_id: string;
  status: string;
  estimated_total: string;
  items: ShoppingItem[];
}

export interface DashboardPlan {
  meal_plan_id: string;
  status: string;
  start_date: string;
  end_date: string;
  budget: string | null;
  meals_total: number;
  meals_cooked: number;
}

export interface UpcomingMeal {
  date: string;
  meal_id: string;
  meal_type: MealType;
  recipe_id: string;
  recipe_title: string;
}

export interface UseSoonAlert {
  name: string;
  quantity: string;
  unit: string;
  expires_on: string;
}

export interface RunningLowAlert {
  name: string;
  quantity: string;
  unit: string;
}

export interface NeededAlert {
  name: string;
  unit: string;
}

export interface Dashboard {
  household_id: string;
  plan: DashboardPlan | null;
  upcoming_meals: UpcomingMeal[];
  alerts: {
    use_soon: UseSoonAlert[];
    running_low: RunningLowAlert[];
    needed_not_stocked: NeededAlert[];
  };
}

export interface GenerateRequest {
  household_id: string;
  start_date: string;
  end_date: string;
  household_size: number;
  meal_types: MealType[];
  dietary: { flags: string[]; avoid_text: string | null };
  budget: number | null;
}

export const api = {
  listHouseholds: () => req<Household[]>("/v1/households"),
  createHousehold: (name: string) =>
    req<Household>("/v1/households", { method: "POST", body: JSON.stringify({ name }) }),
  getPantry: (id: string) => req<PantryItem[]>(`/v1/households/${id}/pantry`),
  getDashboard: (id: string) => req<Dashboard>(`/v1/households/${id}/dashboard`),
  addByBarcode: (householdId: string, barcode: string) =>
    req<{ name: string; quantity: string; unit: string }>(
      `/v1/households/${householdId}/pantry/add-barcode`,
      { method: "POST", body: JSON.stringify({ barcode }) },
    ),
  generate: (body: GenerateRequest) =>
    req<JobAccepted>("/v1/meal-plans/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getJob: (id: string) => req<JobStatus>(`/v1/jobs/${id}`),
  getMealPlan: (id: string) => req<MealPlanDetail>(`/v1/meal-plans/${id}`),
  getRecipe: (id: string) => req<RecipeDetail>(`/v1/recipes/${id}`),
  // The household's latest plan, or null when there's none (404).
  getLatestPlan: async (householdId: string): Promise<MealPlanDetail | null> => {
    try {
      return await req<MealPlanDetail>(`/v1/households/${householdId}/latest-plan`);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("404")) return null;
      throw e;
    }
  },
  buildShoppingList: (mealPlanId: string) =>
    req<ShoppingSummary>("/v1/shopping-lists/build", {
      method: "POST",
      body: JSON.stringify({ meal_plan_id: mealPlanId }),
    }),
  getShoppingList: (id: string) => req<ShoppingListDetail>(`/v1/shopping-lists/${id}`),
  estimatePrices: (id: string) =>
    req<unknown>(`/v1/shopping-lists/${id}/estimate-prices`, { method: "POST", body: "{}" }),
  purchase: (id: string) =>
    req<unknown>(`/v1/shopping-lists/${id}/purchase`, { method: "POST", body: "{}" }),
  cookMeal: (mealId: string) =>
    req<unknown>(`/v1/meals/${mealId}/cook`, { method: "POST", body: "{}" }),
  swapMeal: (mealId: string, modify?: string) =>
    req<{ title: string }>(`/v1/meals/${mealId}/swap`, {
      method: "POST",
      body: JSON.stringify({ modify: modify ?? null }),
    }),
  iterateMeal: (mealId: string, modify: string) =>
    req<{ title: string }>(`/v1/meals/${mealId}/iterate`, {
      method: "POST",
      body: JSON.stringify({ modify }),
    }),
};
