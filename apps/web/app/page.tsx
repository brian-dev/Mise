"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, type Dashboard, type UpcomingMeal } from "../lib/api";
import { Button, Card, Thumb } from "../components/ui";
import { SectionLabel } from "./shell";
import { useWorkspace } from "./workspace";

export default function HomePage() {
  const { householdId, households } = useWorkspace();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [cooking, setCooking] = useState<string | null>(null);

  const refresh = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getDashboard(id));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (householdId) void refresh(householdId);
    else setLoading(false);
  }, [householdId, refresh]);

  // Cook the meal right from the dashboard and refresh the cards in place.
  const cook = useCallback(
    async (mealId: string) => {
      setCooking(mealId);
      setError(null);
      try {
        await api.cookMeal(mealId);
        if (householdId) setData(await api.getDashboard(householdId));
      } catch (e) {
        setError(String(e));
      } finally {
        setCooking(null);
      }
    },
    [householdId],
  );

  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-3xl font-medium tracking-tight">{greeting()}</h1>
        <p className="mt-0.5 text-sm text-muted">
          {longDate()}
          {data?.plan ? ` · ${planSubtitle(data)}` : " · no plan yet"}
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
          {error}
        </div>
      )}

      {households.length === 0 ? (
        <EmptyHousehold />
      ) : loading && !data ? (
        <p className="text-muted">Loading…</p>
      ) : (
        <DashboardGrid data={data} onCook={cook} cooking={cooking} />
      )}
    </div>
  );
}

function greeting(d = new Date()): string {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function longDate(d = new Date()): string {
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function planSubtitle(data: Dashboard): string {
  const p = data.plan!;
  const togo = p.meals_total - p.meals_cooked;
  return `${p.meals_total}-meal plan · ${togo} to go`;
}

function EmptyHousehold() {
  return (
    <Card className="p-6">
      <SectionLabel>Welcome</SectionLabel>
      <h3 className="mt-2 font-display text-xl font-semibold">No household yet</h3>
      <p className="mt-1 text-sm text-muted">
        Create a household on the Plan tab to get started.
      </p>
      <div className="mt-4">
        <Link href="/plan">
          <Button>Go to Plan →</Button>
        </Link>
      </div>
    </Card>
  );
}

function DashboardGrid({
  data,
  onCook,
  cooking,
}: {
  data: Dashboard | null;
  onCook: (mealId: string) => void;
  cooking: string | null;
}) {
  if (!data) return null;
  const tonight = data.upcoming_meals[0];
  const upNext = data.upcoming_meals.slice(1, 4);
  const alerts = data.alerts;
  const alertCount =
    alerts.running_low.length + alerts.needed_not_stocked.length + alerts.use_soon.length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="dashboard">
      {/* Up next */}
      <Card className="p-5">
        <SectionLabel>Up next</SectionLabel>
        {tonight ? (
          <>
            <Link href={`/recipe/${tonight.recipe_id}`} className="mt-2 flex items-center gap-3">
              <Thumb src={tonight.image_url} alt={tonight.recipe_title} size={56} />
              <span>
                <span className="block font-display text-xl font-semibold tracking-tight hover:text-accent-ink">
                  {tonight.recipe_title}
                </span>
                <span className="mt-0.5 block text-sm text-muted">
                  {titleCase(tonight.meal_type)} · {shortDate(tonight.date)}
                </span>
              </span>
            </Link>
            <div className="mt-4 flex gap-2">
              <Button onClick={() => onCook(tonight.meal_id)} disabled={cooking !== null}>
                {cooking === tonight.meal_id ? "Cooking…" : "Cook"}
              </Button>
              <Link href={`/recipe/${tonight.recipe_id}`}>
                <Button variant="ghost">View recipe</Button>
              </Link>
            </div>
          </>
        ) : (
          <>
            <h3 className="mt-2 font-display text-xl font-semibold">Nothing planned</h3>
            <p className="mt-1 text-sm text-muted">Generate a plan to see your meals.</p>
            <div className="mt-4">
              <Link href="/plan">
                <Button>Generate a plan →</Button>
              </Link>
            </div>
          </>
        )}
      </Card>

      {/* This week */}
      <Card className="p-5">
        <SectionLabel>This week</SectionLabel>
        {data.plan ? (
          <>
            <h3 className="mt-2 font-display text-xl font-semibold tracking-tight">
              {shortDate(data.plan.start_date)} – {shortDate(data.plan.end_date)}
            </h3>
            <p className="mt-1 text-sm text-muted">
              {data.plan.meals_total} meals · {data.plan.meals_cooked} cooked,{" "}
              {data.plan.meals_total - data.plan.meals_cooked} to go
            </p>
            {upNext.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-sm">
                {upNext.map((m) => (
                  <UpNextRow key={m.meal_id} meal={m} />
                ))}
              </ul>
            )}
            <div className="mt-4">
              <Link href="/plan">
                <Button variant="ghost">View plan →</Button>
              </Link>
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">No active plan.</p>
        )}
      </Card>

      {/* Heads up */}
      <Card className="p-5 sm:col-span-2">
        <SectionLabel>Heads up</SectionLabel>
        {alertCount === 0 ? (
          <p className="mt-2 text-sm text-muted">
            All clear — pantry looks good and nothing&apos;s expiring soon.
          </p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {alerts.running_low.length > 0 && (
              <AlertRow icon="▢">
                <strong>Running low:</strong> {nameList(alerts.running_low)}
              </AlertRow>
            )}
            {alerts.needed_not_stocked.length > 0 && (
              <AlertRow icon="＋">
                <strong>Needed, not stocked:</strong> {nameList(alerts.needed_not_stocked)}
              </AlertRow>
            )}
            {alerts.use_soon.length > 0 && (
              <AlertRow icon="⏳">
                <strong>Use soon (est.):</strong> {nameList(alerts.use_soon)}
              </AlertRow>
            )}
          </ul>
        )}
        <div className="mt-4 flex gap-2">
          <Link href="/pantry">
            <Button variant="ghost">Add to pantry</Button>
          </Link>
          <Link href="/shopping">
            <Button variant="ghost">Build shopping list</Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}

function UpNextRow({ meal }: { meal: UpcomingMeal }) {
  return (
    <li className="border-b border-line/60 pb-1.5 last:border-0">
      <Link
        href={`/recipe/${meal.recipe_id}`}
        className="flex items-center gap-2.5 hover:text-accent-ink"
      >
        <Thumb src={meal.image_url} alt={meal.recipe_title} size={32} />
        <span className="truncate">{meal.recipe_title}</span>
        <span className="ml-auto shrink-0 text-xs text-muted">
          {titleCase(meal.meal_type)} · {shortDate(meal.date)}
        </span>
      </Link>
    </li>
  );
}

function AlertRow({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span className="select-none text-muted">{icon}</span>
      <span>{children}</span>
    </li>
  );
}

function nameList(items: { name: string }[]): string {
  return items.map((i) => i.name).join(", ");
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
