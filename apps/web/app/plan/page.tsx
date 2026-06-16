"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MEAL_TYPES, type MealType } from "@mise/shared";

import { api } from "../../lib/api";
import { Button, Card, InfoTip, Input, Thumb } from "../../components/ui";
import { CuisineSelector } from "../../components/cuisine-selector";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

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
    regenerateDay,
    removeMeal,
    buildList,
  } = useWorkspace();

  const [newName, setNewName] = useState("");
  const [startDate, setStartDate] = useState(todayISO());
  const [days, setDays] = useState(3);
  const endDate = addDays(startDate, days - 1);
  const [size, setSize] = useState(2);
  const [mealTypes, setMealTypes] = useState<MealType[]>(["dinner"]);
  const [flags, setFlags] = useState("");
  const [avoid, setAvoid] = useState("");
  const [budget, setBudget] = useState("");
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [customizeOpen, setCustomizeOpen] = useState(false);

  // Pre-fill the form from the household profile (set during onboarding / Settings).
  useEffect(() => {
    if (!householdId) return;
    api
      .getProfile(householdId)
      .then((p) => {
        if (p.household_size) setSize(p.household_size);
        const meals = (p.preferred_meal_types ?? []).filter((m): m is MealType =>
          (MEAL_TYPES as readonly string[]).includes(m),
        );
        if (meals.length) setMealTypes(meals);
        if (p.weekly_budget) setBudget(p.weekly_budget);
        if (p.preferred_cuisines?.length) setCuisines(p.preferred_cuisines);
        if (p.dietary_flags?.length) setFlags(p.dietary_flags.join(", "));
        if (p.avoid_text) setAvoid(p.avoid_text);
      })
      .catch(() => {}); // no profile yet -> keep defaults
  }, [householdId]);

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
      cuisines,
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

  const generating = busy === "generate";
  const genLabel = generating
    ? genStatus === "running"
      ? "Running…"
      : genStatus === "queued"
        ? "Queued…"
        : "Starting…"
    : "Generate plan";

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
            <Button onClick={() => createHousehold(newName)} disabled={busy === "household"}>
              Create
            </Button>
          </div>
        </Card>
      )}

      {/* Generate — defaults from the profile; details behind "Customize". */}
      <Card className="p-5">
        <SectionLabel>Generate a plan</SectionLabel>
        <p className="mt-2 text-sm text-muted">
          {summary({ size, mealTypes, startDate, endDate, days, budget, cuisines })}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            data-testid="generate"
            onClick={onGenerate}
            disabled={!householdId || mealTypes.length === 0 || generating}
          >
            {genLabel}
          </Button>
          <button
            type="button"
            onClick={() => setCustomizeOpen((o) => !o)}
            className="text-sm font-medium text-muted hover:text-ink"
            data-testid="plan-customize"
          >
            {customizeOpen ? "Hide options ▴" : "Customize ▾"}
          </button>
          {generating && (
            <span className="text-sm text-muted">
              job {genStatus ?? "queued"} — this can take 30–60s for multi-day plans
            </span>
          )}
        </div>

        {customizeOpen && (
          <div className="mt-5 border-t border-line pt-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field label="Start">
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </Field>
              <Field label="Days">
                <Input
                  type="number"
                  min={1}
                  max={14}
                  value={days}
                  onChange={(e) =>
                    setDays(Math.min(14, Math.max(1, Number(e.target.value) || 1)))
                  }
                />
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
                <Input value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="optional" />
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

            <div className="mt-4">
              <span className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Cuisines
                </span>
                <InfoTip label="Cuisines">
                  Cuisines you&apos;d like the plan to lean toward. Most meals will be on-list,
                  with the occasional wildcard for variety. Leave empty for no preference.
                </InfoTip>
              </span>
              <div className="mt-2">
                <CuisineSelector selected={cuisines} onChange={setCuisines} />
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field
                label="Dietary flags"
                info="Diets every meal must follow. Comma-separated, e.g. vegetarian, vegan, gluten-free, dairy-free. Leave blank for no restrictions."
              >
                <Input
                  placeholder="e.g. vegetarian, gluten-free"
                  value={flags}
                  onChange={(e) => setFlags(e.target.value)}
                />
              </Field>
              <Field
                label="Avoid"
                info="Ingredients or things to keep out, in plain words — e.g. no mushrooms, no shellfish, not too spicy. The planner works around these."
              >
                <Input
                  placeholder="e.g. no mushrooms, no pork"
                  value={avoid}
                  onChange={(e) => setAvoid(e.target.value)}
                />
              </Field>
            </div>
          </div>
        )}
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
                <div className="flex items-center justify-between">
                  <div className="font-display text-base font-semibold">{shortDate(d.date)}</div>
                  <SmallButton
                    data-testid="regenerate-day"
                    onClick={() => regenerateDay(d.date)}
                    disabled={!!busy}
                  >
                    {busy === `regen-${d.date}` ? "Regenerating…" : "↻ Regenerate day"}
                  </SmallButton>
                </div>
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
                        <button
                          onClick={() => removeMeal(m.meal_id)}
                          disabled={!!busy}
                          aria-label={`Remove ${m.recipe_title}`}
                          data-testid="remove-meal"
                          className="text-muted hover:text-accent-ink disabled:opacity-50"
                        >
                          ✕
                        </button>
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

function summary({
  size,
  mealTypes,
  startDate,
  endDate,
  days,
  budget,
  cuisines,
}: {
  size: number;
  mealTypes: MealType[];
  startDate: string;
  endDate: string;
  days: number;
  budget: string;
  cuisines: string[];
}): string {
  const dateLabel =
    days === 1 ? shortDate(startDate) : `${shortDate(startDate)}–${shortDate(endDate)}`;
  const parts = [
    `${days} ${days === 1 ? "day" : "days"}`,
    `${size} ${size === 1 ? "person" : "people"}`,
    mealTypes.length ? mealTypes.join(", ") : "no meals selected",
    dateLabel,
  ];
  if (budget) parts.push(`~$${budget}`);
  if (cuisines.length) parts.push(cuisines.slice(0, 3).join(", ") + (cuisines.length > 3 ? "…" : ""));
  return parts.join(" · ");
}

function Field({
  label,
  info,
  children,
}: {
  label: string;
  info?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="block">
      <span className="flex items-center gap-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          {label}
        </span>
        {info && <InfoTip label={label}>{info}</InfoTip>}
      </span>
      <div className="mt-1">{children}</div>
    </div>
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
