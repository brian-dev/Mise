"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import type { MealType } from "@mise/shared";

import {
  api,
  type Household,
  type MealPlanDetail,
  type PantryItem,
  type ShoppingListDetail,
} from "../lib/api";
import { waitForJob } from "../lib/jobs";

/**
 * Shared app state for the signed-in workspace. Lifts what was the dev-harness
 * component state into a context so the Plan / Shopping / Pantry screens (now
 * separate routes) operate on the same household, plan, and shopping list.
 *
 * The action methods mirror the original harness behavior exactly so the core
 * loop (and its E2E selectors) keep working under the new navigation.
 */

export interface GenerateInput {
  start_date: string;
  end_date: string;
  household_size: number;
  meal_types: MealType[];
  flags: string;
  avoid: string;
  budget: string;
  cuisines: string[];
}

interface Workspace {
  households: Household[];
  householdId: string;
  setHouseholdId: (id: string) => void;
  createHousehold: (name: string) => Promise<void>;

  pantry: PantryItem[];
  plan: MealPlanDetail | null;
  shopping: ShoppingListDetail | null;

  busy: string | null;
  genStatus: string | null;
  error: string | null;

  generate: (input: GenerateInput) => Promise<void>;
  cook: (mealId: string) => Promise<void>;
  swap: (mealId: string) => Promise<void>;
  iterate: (mealId: string, modify: string) => Promise<void>;
  buildList: () => Promise<string | null>;
  estimatePrices: () => Promise<void>;
  purchase: () => Promise<void>;
  toggleItem: (itemId: string, checked: boolean) => Promise<void>;
  addItem: (name: string) => Promise<void>;
  removeItem: (itemId: string) => Promise<void>;
  addBarcode: (barcode: string) => Promise<void>;
}

const KEY = "mise-household";
const Ctx = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [households, setHouseholds] = useState<Household[]>([]);
  const [householdId, setHouseholdIdState] = useState<string>("");
  const [pantry, setPantry] = useState<PantryItem[]>([]);
  const [plan, setPlan] = useState<MealPlanDetail | null>(null);
  const [shopping, setShopping] = useState<ShoppingListDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [genStatus, setGenStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setHouseholdId = useCallback((id: string) => {
    setHouseholdIdState(id);
    if (id) localStorage.setItem(KEY, id);
  }, []);

  const refreshHouseholds = useCallback(async () => {
    const hs = await api.listHouseholds();
    setHouseholds(hs);
    return hs;
  }, []);

  const refreshPantry = useCallback(async (id: string) => {
    if (id) setPantry(await api.getPantry(id));
  }, []);

  // Initial load: households, then restore the saved/first household.
  useEffect(() => {
    refreshHouseholds()
      .then((hs) => {
        const saved = localStorage.getItem(KEY);
        const pick = hs.find((h) => h.id === saved) ?? hs[0];
        if (pick) setHouseholdIdState(pick.id);
      })
      .catch((e) => setError(String(e)));
  }, [refreshHouseholds]);

  // When the household changes, load its pantry + latest plan, clear shopping.
  useEffect(() => {
    if (!householdId) return;
    setShopping(null);
    refreshPantry(householdId).catch((e) => setError(String(e)));
    api
      .getLatestPlan(householdId)
      .then(setPlan)
      .catch((e) => setError(String(e)));
  }, [householdId, refreshPantry]);

  const run = useCallback(async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }, []);

  const createHousehold = useCallback(
    (name: string) =>
      run("household", async () => {
        const h = await api.createHousehold(name || "My Household");
        await refreshHouseholds();
        setHouseholdId(h.id);
      }),
    [run, refreshHouseholds, setHouseholdId],
  );

  const generate = useCallback(
    (input: GenerateInput) =>
      run("generate", async () => {
        setShopping(null);
        setPlan(null);
        const { job_id } = await api.generate({
          household_id: householdId,
          start_date: input.start_date,
          end_date: input.end_date,
          household_size: input.household_size,
          meal_types: input.meal_types,
          dietary: {
            flags: input.flags.split(",").map((s) => s.trim()).filter(Boolean),
            avoid_text: input.avoid || null,
          },
          budget: input.budget ? Number(input.budget) : null,
          cuisines: input.cuisines,
        });
        try {
          const job = await waitForJob(job_id, setGenStatus);
          const id = job.result?.meal_plan_id;
          if (id) setPlan(await api.getMealPlan(id));
        } finally {
          setGenStatus(null);
        }
      }),
    [run, householdId],
  );

  const cook = useCallback(
    (mealId: string) =>
      run(`cook-${mealId}`, async () => {
        await api.cookMeal(mealId);
        if (plan) setPlan(await api.getMealPlan(plan.meal_plan_id));
        await refreshPantry(householdId);
      }),
    [run, plan, householdId, refreshPantry],
  );

  const swap = useCallback(
    (mealId: string) =>
      run(`swap-${mealId}`, async () => {
        await api.swapMeal(mealId);
        if (plan) setPlan(await api.getMealPlan(plan.meal_plan_id));
      }),
    [run, plan],
  );

  const iterate = useCallback(
    (mealId: string, modify: string) =>
      run(`iterate-${mealId}`, async () => {
        await api.iterateMeal(mealId, modify);
        if (plan) setPlan(await api.getMealPlan(plan.meal_plan_id));
      }),
    [run, plan],
  );

  const buildList = useCallback(async (): Promise<string | null> => {
    if (!plan) return null;
    let listId: string | null = null;
    await run("shopping", async () => {
      const summary = await api.buildShoppingList(plan.meal_plan_id);
      setShopping(await api.getShoppingList(summary.shopping_list_id));
      listId = summary.shopping_list_id;
    });
    return listId;
  }, [run, plan]);

  const estimatePrices = useCallback(
    () =>
      run("estimate", async () => {
        if (!shopping) return;
        await api.estimatePrices(shopping.shopping_list_id);
        setShopping(await api.getShoppingList(shopping.shopping_list_id));
      }),
    [run, shopping],
  );

  const purchase = useCallback(
    () =>
      run("purchase", async () => {
        if (!shopping) return;
        await api.purchase(shopping.shopping_list_id);
        setShopping(await api.getShoppingList(shopping.shopping_list_id));
        await refreshPantry(householdId);
      }),
    [run, shopping, householdId, refreshPantry],
  );

  // Optimistic check/uncheck (instant feedback while shopping); reverts on error.
  const toggleItem = useCallback(
    async (itemId: string, checked: boolean) => {
      if (!shopping) return;
      const listId = shopping.shopping_list_id;
      setShopping((s) =>
        s
          ? {
              ...s,
              items: s.items.map((it) =>
                it.id === itemId ? { ...it, is_checked: checked } : it,
              ),
            }
          : s,
      );
      try {
        await api.patchShoppingItem(listId, itemId, { is_checked: checked });
      } catch {
        setShopping(await api.getShoppingList(listId)); // revert to server truth
      }
    },
    [shopping],
  );

  const addItem = useCallback(
    (name: string) =>
      run("add-item", async () => {
        if (!shopping) return;
        await api.addShoppingItem(shopping.shopping_list_id, { name });
        setShopping(await api.getShoppingList(shopping.shopping_list_id));
      }),
    [run, shopping],
  );

  const removeItem = useCallback(
    (itemId: string) =>
      run(`remove-${itemId}`, async () => {
        if (!shopping) return;
        await api.deleteShoppingItem(shopping.shopping_list_id, itemId);
        setShopping(await api.getShoppingList(shopping.shopping_list_id));
      }),
    [run, shopping],
  );

  const addBarcode = useCallback(
    (barcode: string) =>
      run("barcode", async () => {
        if (!householdId || !barcode.trim()) return;
        await api.addByBarcode(householdId, barcode.trim());
        await refreshPantry(householdId);
      }),
    [run, householdId, refreshPantry],
  );

  const value: Workspace = {
    households,
    householdId,
    setHouseholdId,
    createHousehold,
    pantry,
    plan,
    shopping,
    busy,
    genStatus,
    error,
    generate,
    cook,
    swap,
    iterate,
    buildList,
    estimatePrices,
    purchase,
    toggleItem,
    addItem,
    removeItem,
    addBarcode,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace(): Workspace {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
