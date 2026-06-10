"use client";

import { useCallback, useEffect, useState } from "react";

import { MEAL_TYPES, type MealType } from "@mise/shared";

import {
  api,
  type Household,
  type MealPlanDetail,
  type PantryItem,
  type ShoppingListDetail,
} from "../lib/api";
import { Login, SignOutButton, useSession } from "./auth";

const card: React.CSSProperties = {
  border: "1px solid #e2ddd2",
  borderRadius: 10,
  padding: "1rem 1.25rem",
  marginBottom: "1rem",
  background: "#fff",
};

export default function Page() {
  const session = useSession();
  if (session === undefined) return null; // loading
  if (session === null) return <Login />;
  return <Home email={session.user.email} />;
}

function Home({ email }: { email?: string }) {
  const [households, setHouseholds] = useState<Household[]>([]);
  const [householdId, setHouseholdId] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [pantry, setPantry] = useState<PantryItem[]>([]);

  // Generation form
  const [startDate, setStartDate] = useState("2026-06-10");
  const [endDate, setEndDate] = useState("2026-06-12");
  const [size, setSize] = useState(2);
  const [mealTypes, setMealTypes] = useState<MealType[]>(["dinner"]);
  const [flags, setFlags] = useState("vegetarian");
  const [avoid, setAvoid] = useState("no mushrooms");
  const [budget, setBudget] = useState("60");

  const [plan, setPlan] = useState<MealPlanDetail | null>(null);
  const [shopping, setShopping] = useState<ShoppingListDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [genStatus, setGenStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshHouseholds = useCallback(async () => {
    setHouseholds(await api.listHouseholds());
  }, []);

  const refreshPantry = useCallback(async (id: string) => {
    if (id) setPantry(await api.getPantry(id));
  }, []);

  useEffect(() => {
    refreshHouseholds().catch((e) => setError(String(e)));
  }, [refreshHouseholds]);

  useEffect(() => {
    if (!householdId) return;
    refreshPantry(householdId).catch((e) => setError(String(e)));
    // Load the household's existing plan (if any) so it shows without regenerating.
    setShopping(null);
    api
      .getLatestPlan(householdId)
      .then(setPlan)
      .catch((e) => setError(String(e)));
  }, [householdId, refreshPantry]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  const createHousehold = () =>
    run("household", async () => {
      const h = await api.createHousehold(newName || "My Household");
      setNewName("");
      await refreshHouseholds();
      setHouseholdId(h.id);
    });

  const toggleMeal = (m: MealType) =>
    setMealTypes((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const generate = () =>
    run("generate", async () => {
      setShopping(null);
      setPlan(null);
      const { job_id } = await api.generate({
        household_id: householdId,
        start_date: startDate,
        end_date: endDate,
        household_size: size,
        meal_types: mealTypes,
        dietary: {
          flags: flags.split(",").map((s) => s.trim()).filter(Boolean),
          avoid_text: avoid || null,
        },
        budget: budget ? Number(budget) : null,
      });

      // Poll the job until it finishes (Realtime push is a later enhancement).
      try {
        for (;;) {
          const job = await api.getJob(job_id);
          setGenStatus(job.status);
          if (job.status === "done") {
            const id = job.result?.meal_plan_id;
            if (id) setPlan(await api.getMealPlan(id));
            return;
          }
          if (job.status === "failed") {
            throw new Error(job.error ?? "generation failed");
          }
          await new Promise((r) => setTimeout(r, 1500));
        }
      } finally {
        setGenStatus(null);
      }
    });

  const buildList = () =>
    run("shopping", async () => {
      if (!plan) return;
      const summary = await api.buildShoppingList(plan.meal_plan_id);
      setShopping(await api.getShoppingList(summary.shopping_list_id));
    });

  const cook = (mealId: string) =>
    run(`cook-${mealId}`, async () => {
      await api.cookMeal(mealId);
      if (plan) setPlan(await api.getMealPlan(plan.meal_plan_id));
      await refreshPantry(householdId);
    });

  const swap = (mealId: string) =>
    run(`swap-${mealId}`, async () => {
      await api.swapMeal(mealId);
      if (plan) setPlan(await api.getMealPlan(plan.meal_plan_id));
    });

  const estimatePrices = () =>
    run("estimate", async () => {
      if (!shopping) return;
      await api.estimatePrices(shopping.shopping_list_id);
      setShopping(await api.getShoppingList(shopping.shopping_list_id));
    });

  const markPurchased = () =>
    run("purchase", async () => {
      if (!shopping) return;
      await api.purchase(shopping.shopping_list_id);
      setShopping(await api.getShoppingList(shopping.shopping_list_id));
      await refreshPantry(householdId);
    });

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 760, margin: "0 auto", padding: "2rem 1rem" }}>
      <SignOutButton email={email} />
      <h1 style={{ marginBottom: 4 }}>Mise — dev harness</h1>
      <p style={{ color: "#6b6256", marginTop: 0 }}>Verify the core loop end-to-end.</p>

      {error && (
        <div style={{ ...card, borderColor: "#c0392b", color: "#c0392b", whiteSpace: "pre-wrap" }}>
          {error}
        </div>
      )}

      {/* Household */}
      <section style={card}>
        <h2>1 · Household</h2>
        <select
          data-testid="household-select"
          value={householdId}
          onChange={(e) => setHouseholdId(e.target.value)}
          style={{ padding: 6 }}
        >
          <option value="">— select —</option>
          {households.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}
            </option>
          ))}
        </select>
        <div style={{ marginTop: 8 }}>
          <input
            placeholder="New household name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ padding: 6 }}
          />
          <button onClick={createHousehold} disabled={busy === "household"} style={{ marginLeft: 8 }}>
            Create
          </button>
        </div>
        {householdId && (
          <div style={{ marginTop: 10 }}>
            <strong>Pantry</strong>
            {pantry.length === 0 ? (
              <div style={{ color: "#6b6256" }}>empty</div>
            ) : (
              <ul style={{ margin: "4px 0" }}>
                {pantry.map((p) => (
                  <li key={`${p.name}-${p.unit}`}>
                    {p.quantity} {p.unit} {p.name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Generate */}
      <section style={card}>
        <h2>2 · Generate a plan</h2>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label>
            Start <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            End <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label>
            Household size{" "}
            <input
              type="number"
              min={1}
              value={size}
              onChange={(e) => setSize(Number(e.target.value))}
              style={{ width: 56 }}
            />
          </label>
          <label>
            Budget $<input value={budget} onChange={(e) => setBudget(e.target.value)} style={{ width: 70 }} />
          </label>
        </div>
        <div style={{ marginTop: 8 }}>
          Meals:{" "}
          {MEAL_TYPES.map((m) => (
            <label key={m} style={{ marginRight: 10 }}>
              <input type="checkbox" checked={mealTypes.includes(m)} onChange={() => toggleMeal(m)} /> {m}
            </label>
          ))}
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label>
            Dietary flags <input value={flags} onChange={(e) => setFlags(e.target.value)} />
          </label>
          <label>
            Avoid <input value={avoid} onChange={(e) => setAvoid(e.target.value)} />
          </label>
        </div>
        <button
          data-testid="generate"
          onClick={generate}
          disabled={!householdId || mealTypes.length === 0 || busy === "generate"}
          style={{ marginTop: 12 }}
        >
          {busy === "generate"
            ? genStatus === "running"
              ? "Running… (Claude is generating)"
              : genStatus === "queued"
                ? "Queued…"
                : "Starting…"
            : "Generate plan"}
        </button>
        {busy === "generate" && (
          <span style={{ marginLeft: 10, color: "#6b6256" }}>
            job {genStatus ?? "queued"} — this can take 30–60s for multi-day plans
          </span>
        )}
      </section>

      {/* Plan */}
      {plan && (
        <section style={card}>
          <h2>3 · Plan ({plan.status})</h2>
          {plan.days.map((d) => (
            <div key={d.date} style={{ marginBottom: 8 }}>
              <strong>{d.date}</strong>
              {d.meals.map((m) => (
                <div key={m.meal_id} data-testid="meal-row" style={{ marginLeft: 12 }}>
                  [{m.meal_type}] <span data-testid="recipe-title">{m.recipe_title}</span> —{" "}
                  {m.servings} servings{" "}
                  {m.cooked_at ? (
                    <span data-testid="cooked" style={{ color: "#2e7d32" }}>
                      ✓ cooked
                    </span>
                  ) : (
                    <>
                      <button data-testid="cook" onClick={() => cook(m.meal_id)} disabled={!!busy}>
                        Cook
                      </button>{" "}
                      <button data-testid="swap" onClick={() => swap(m.meal_id)} disabled={!!busy}>
                        {busy === `swap-${m.meal_id}` ? "Swapping…" : "Swap"}
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          ))}
          <button
            data-testid="build-shopping"
            onClick={buildList}
            disabled={busy === "shopping"}
            style={{ marginTop: 8 }}
          >
            Build shopping list
          </button>
        </section>
      )}

      {/* Shopping list */}
      {shopping && (
        <section style={card} data-testid="shopping-list">
          <h2>4 · Shopping list ({shopping.status})</h2>
          <div>
            Estimated total: <strong data-testid="estimated-total">${shopping.estimated_total}</strong>
            {shopping.items.some((it) => it.estimated_price === null) && (
              <em style={{ color: "#6b6256" }}> (some items not yet priced)</em>
            )}
          </div>
          {shopping.status !== "purchased" && (
            <div style={{ marginTop: 8 }}>
              {shopping.items.some((it) => it.estimated_price === null) && (
                <button
                  data-testid="estimate-prices"
                  onClick={estimatePrices}
                  disabled={busy === "estimate"}
                  style={{ marginRight: 8 }}
                >
                  {busy === "estimate" ? "Estimating…" : "Estimate remaining prices"}
                </button>
              )}
              <button data-testid="purchase" onClick={markPurchased} disabled={busy === "purchase"}>
                Mark purchased (restock pantry)
              </button>
            </div>
          )}
          <table style={{ marginTop: 8, borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e2ddd2" }}>
                <th>Item</th>
                <th>Qty</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              {shopping.items.map((it) => (
                <tr key={`${it.name}-${it.unit}`}>
                  <td>{it.name}</td>
                  <td>
                    {it.quantity_needed} {it.unit}
                  </td>
                  <td>{it.estimated_price ? `$${it.estimated_price}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
