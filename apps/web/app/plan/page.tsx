"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MEAL_TYPES, type MealType } from "@mise/shared";

import { Button, Card, Input, Thumb } from "../../components/ui";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

export default function PlanPage() {
  const router = useRouter();
  const {
    households,
    householdId,
    createHousehold,
    plan,
    busy,
    genStatus,
    generate,
    cook,
    swap,
    iterate,
    buildList,
  } = useWorkspace();

  const [newName, setNewName] = useState("");
  const [startDate, setStartDate] = useState("2026-06-12");
  const [endDate, setEndDate] = useState("2026-06-14");
  const [size, setSize] = useState(2);
  const [mealTypes, setMealTypes] = useState<MealType[]>(["dinner"]);
  const [flags, setFlags] = useState("vegetarian");
  const [avoid, setAvoid] = useState("no mushrooms");
  const [budget, setBudget] = useState("60");

  const toggleMeal = (m: MealType) =>
    setMealTypes((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const onGenerate = () =>
    generate({
      start_date: startDate,
      end_date: endDate,
      household_size: size,
      meal_types: mealTypes,
      flags,
      avoid,
      budget,
    });

  const onBuildList = async () => {
    const id = await buildList();
    if (id) router.push("/shopping");
  };

  const onIterate = (mealId: string) => {
    const modify = window.prompt(
      'How should I change this dish? (e.g. "spicier", "make it vegan")',
    );
    if (modify) void iterate(mealId, modify);
  };

  return (
    <div className="space-y-4">
      {households.length === 0 && (
        <Card className="p-5">
          <SectionLabel>Get started</SectionLabel>
          <h3 className="mt-2 font-display text-lg font-semibold">Create a household</h3>
          <div className="mt-3 flex gap-2">
            <Input
              placeholder="Household name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <Button
              onClick={() => createHousehold(newName)}
              disabled={busy === "household"}
            >
              Create
            </Button>
          </div>
        </Card>
      )}

      {/* Generation form */}
      <Card className="p-5">
        <SectionLabel>Generate a plan</SectionLabel>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Start">
            <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label="End">
            <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
          <Field label="Household size">
            <Input
              type="number"
              min={1}
              value={size}
              onChange={(e) => setSize(Number(e.target.value))}
            />
          </Field>
          <Field label="Budget ($)">
            <Input value={budget} onChange={(e) => setBudget(e.target.value)} />
          </Field>
        </div>

        <div className="mt-4">
          <SectionLabel>Meals</SectionLabel>
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            {MEAL_TYPES.map((m) => (
              <label key={m} className="flex items-center gap-1.5 capitalize">
                <input
                  type="checkbox"
                  checked={mealTypes.includes(m)}
                  onChange={() => toggleMeal(m)}
                  className="accent-accent"
                />
                {m}
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Dietary flags">
            <Input value={flags} onChange={(e) => setFlags(e.target.value)} />
          </Field>
          <Field label="Avoid">
            <Input value={avoid} onChange={(e) => setAvoid(e.target.value)} />
          </Field>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button
            data-testid="generate"
            onClick={onGenerate}
            disabled={!householdId || mealTypes.length === 0 || busy === "generate"}
          >
            {busy === "generate"
              ? genStatus === "running"
                ? "Running…"
                : genStatus === "queued"
                  ? "Queued…"
                  : "Starting…"
              : "Generate plan"}
          </Button>
          {busy === "generate" && (
            <span className="text-sm text-muted">
              job {genStatus ?? "queued"} — this can take 30–60s for multi-day plans
            </span>
          )}
        </div>
      </Card>

      {/* Plan */}
      {plan && (
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <SectionLabel>Plan · {plan.status}</SectionLabel>
            <Button
              data-testid="build-shopping"
              variant="ghost"
              onClick={onBuildList}
              disabled={busy === "shopping"}
            >
              {busy === "shopping" ? "Building…" : "Build shopping list →"}
            </Button>
          </div>

          <div className="mt-3 space-y-4">
            {plan.days.map((d) => (
              <div key={d.date}>
                <div className="font-display text-base font-semibold">{shortDate(d.date)}</div>
                <ul className="mt-1.5 space-y-1.5">
                  {d.meals.map((m) => (
                    <li
                      key={m.meal_id}
                      data-testid="meal-row"
                      className="flex flex-wrap items-center gap-2 border-b border-line/60 py-1.5 text-sm last:border-0"
                    >
                      <span className="w-16 shrink-0 text-xs uppercase tracking-wide text-muted">
                        {m.meal_type}
                      </span>
                      <Thumb src={m.image_url} alt={m.recipe_title} size={36} />
                      <Link
                        href={`/recipe/${m.recipe_id}`}
                        data-testid="recipe-title"
                        className="font-medium hover:text-accent-ink hover:underline"
                      >
                        {m.recipe_title}
                      </Link>
                      <span className="text-muted">· {m.servings} servings</span>
                      <span className="ml-auto flex items-center gap-2">
                        {m.cooked_at ? (
                          <span data-testid="cooked" className="font-medium text-good">
                            ✓ cooked
                          </span>
                        ) : (
                          <>
                            <SmallButton data-testid="cook" onClick={() => cook(m.meal_id)} disabled={!!busy}>
                              Cook
                            </SmallButton>
                            <SmallButton data-testid="swap" onClick={() => swap(m.meal_id)} disabled={!!busy}>
                              {busy === `swap-${m.meal_id}` ? "Swapping…" : "Swap"}
                            </SmallButton>
                            <SmallButton data-testid="iterate" onClick={() => onIterate(m.meal_id)} disabled={!!busy}>
                              {busy === `iterate-${m.meal_id}` ? "Modifying…" : "Modify"}
                            </SmallButton>
                          </>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function SmallButton({
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`rounded border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink transition-colors hover:bg-surface-2 disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
