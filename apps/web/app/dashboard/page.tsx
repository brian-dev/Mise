"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type Dashboard,
  type Household,
  type UpcomingMeal,
} from "../../lib/api";
import { Button, Card } from "../../components/ui";
import { Login, SignOutButton, useSession } from "../auth";

export default function DashboardPage() {
  const session = useSession();
  if (session === undefined) return null; // loading
  if (session === null) return <Login />;
  return <DashboardHome email={session.user.email} />;
}

/** Friendly date like "Wednesday, June 10". */
function longDate(d = new Date()): string {
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function greeting(d = new Date()): string {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function DashboardHome({ email }: { email?: string }) {
  const [households, setHouseholds] = useState<Household[]>([]);
  const [householdId, setHouseholdId] = useState<string>("");
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listHouseholds()
      .then((hs) => {
        setHouseholds(hs);
        if (hs[0]) setHouseholdId(hs[0].id);
        else setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, []);

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
  }, [householdId, refresh]);

  const firstName = useMemo(() => (email ? email.split("@")[0] : ""), [email]);

  return (
    <main className="min-h-screen bg-bg">
      <div className="mx-auto max-w-3xl px-5 pb-16 pt-7">
        {/* Header */}
        <header className="mb-6 flex items-center justify-between">
          <div className="font-display text-xl font-semibold tracking-tight">
            Mise<span className="text-accent">.</span>
          </div>
          <div className="flex items-center gap-3">
            {households.length > 1 && (
              <select
                data-testid="household-select"
                value={householdId}
                onChange={(e) => setHouseholdId(e.target.value)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink"
              >
                {households.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            )}
            <SignOutButton email={email} />
          </div>
        </header>

        {/* Greeting */}
        <div className="mb-5">
          <h1 className="font-display text-3xl font-medium tracking-tight">
            {greeting()}
            {firstName ? `, ${titleCase(firstName)}` : ""}
          </h1>
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

        {loading && !data ? (
          <p className="text-muted">Loading…</p>
        ) : households.length === 0 ? (
          <EmptyHousehold />
        ) : (
          <DashboardGrid data={data} onRefresh={() => refresh(householdId)} />
        )}
      </div>
    </main>
  );
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
        Create a household in the planner to get started.
      </p>
      <div className="mt-4">
        <a href="/">
          <Button>Open planner →</Button>
        </a>
      </div>
    </Card>
  );
}

function DashboardGrid({
  data,
  onRefresh,
}: {
  data: Dashboard | null;
  onRefresh: () => void;
}) {
  if (!data) return null;
  const tonight = data.upcoming_meals[0];
  const upNext = data.upcoming_meals.slice(1, 4);
  const alerts = data.alerts;
  const alertCount =
    alerts.running_low.length + alerts.needed_not_stocked.length + alerts.use_soon.length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="dashboard">
      {/* Next meal */}
      <Card className="p-5">
        <SectionLabel>Up next</SectionLabel>
        {tonight ? (
          <>
            <h3 className="mt-2 font-display text-xl font-semibold tracking-tight">
              {tonight.recipe_title}
            </h3>
            <p className="mt-1 text-sm text-muted">
              {titleCase(tonight.meal_type)} · {shortDate(tonight.date)}
            </p>
            <div className="mt-4 flex gap-2">
              <a href="/">
                <Button>Cook</Button>
              </a>
              <a href="/">
                <Button variant="ghost">View recipe</Button>
              </a>
            </div>
          </>
        ) : (
          <>
            <h3 className="mt-2 font-display text-xl font-semibold">Nothing planned</h3>
            <p className="mt-1 text-sm text-muted">Generate a plan to see your meals.</p>
            <div className="mt-4">
              <a href="/">
                <Button>Generate a plan →</Button>
              </a>
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
              <a href="/">
                <Button variant="ghost">View plan →</Button>
              </a>
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">No active plan.</p>
        )}
      </Card>

      {/* Heads up — alerts */}
      <Card className="p-5 sm:col-span-2">
        <SectionLabel>Heads up</SectionLabel>
        {alertCount === 0 ? (
          <p className="mt-2 text-sm text-muted">
            All clear — pantry looks good and nothing's expiring soon.
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
          <a href="/">
            <Button variant="ghost">Add to pantry</Button>
          </a>
          <a href="/">
            <Button variant="ghost">Build shopping list</Button>
          </a>
        </div>
      </Card>
    </div>
  );
}

function UpNextRow({ meal }: { meal: UpcomingMeal }) {
  return (
    <li className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-1.5 last:border-0">
      <span className="truncate">{meal.recipe_title}</span>
      <span className="shrink-0 text-xs text-muted">
        {titleCase(meal.meal_type)} · {shortDate(meal.date)}
      </span>
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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
      {children}
    </span>
  );
}

function nameList(items: { name: string }[]): string {
  return items.map((i) => i.name).join(", ");
}

/** "Jun 10" from an ISO date string. */
function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
