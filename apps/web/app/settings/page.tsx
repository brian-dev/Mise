"use client";

import { useEffect, useState } from "react";

import { MEAL_TYPES, type MealType } from "@mise/shared";

import { api } from "../../lib/api";
import { Button, Card, Input } from "../../components/ui";
import { CuisineSelector } from "../../components/cuisine-selector";
import { SectionLabel } from "../shell";
import { THEME_LABELS, THEMES, useTheme, type Theme } from "../theme";
import { useWorkspace } from "../workspace";

const COOKING_TIMES = [
  { value: "quick", label: "Quick & easy" },
  { value: "standard", label: "Balanced" },
  { value: "elaborate", label: "I love to cook" },
];

export default function SettingsPage() {
  return (
    <div className="space-y-4">
      <ProfileEditor />
      <Appearance />
    </div>
  );
}

function ProfileEditor() {
  const { householdId, households } = useWorkspace();
  const [size, setSize] = useState(2);
  const [mealTypes, setMealTypes] = useState<MealType[]>(["dinner"]);
  const [budget, setBudget] = useState("");
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [flags, setFlags] = useState("");
  const [avoid, setAvoid] = useState("");
  const [region, setRegion] = useState("");
  const [store, setStore] = useState("");
  const [cookingTime, setCookingTime] = useState("standard");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!householdId) return;
    setLoaded(false);
    api
      .getProfile(householdId)
      .then((p) => {
        if (p.household_size) setSize(p.household_size);
        const meals = (p.preferred_meal_types ?? []).filter((m): m is MealType =>
          (MEAL_TYPES as readonly string[]).includes(m),
        );
        if (meals.length) setMealTypes(meals);
        setBudget(p.weekly_budget ?? "");
        setCuisines(p.preferred_cuisines ?? []);
        setFlags((p.dietary_flags ?? []).join(", "));
        setAvoid(p.avoid_text ?? "");
        setRegion(p.region ?? "");
        setStore(p.store_preference ?? "");
        setCookingTime(p.cooking_time ?? "standard");
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [householdId]);

  const toggleMeal = (m: MealType) =>
    setMealTypes((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const save = async () => {
    if (!householdId) return;
    setSaving(true);
    setSaved(false);
    try {
      await api.putProfile(householdId, {
        household_size: size,
        weekly_budget: budget || null,
        preferred_cuisines: cuisines,
        preferred_meal_types: mealTypes,
        cooking_time: cookingTime,
        dietary_flags: flags.split(",").map((s) => s.trim()).filter(Boolean),
        avoid_text: avoid || null,
        region: region || null,
        store_preference: store || null,
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (households.length === 0) {
    return (
      <Card className="p-5">
        <SectionLabel>Household profile</SectionLabel>
        <p className="mt-2 text-sm text-muted">Create a household to set preferences.</p>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <SectionLabel>Household profile</SectionLabel>
      <p className="mt-1 text-sm text-muted">
        Your defaults for new plans. Change anytime — the Plan form picks these up.
      </p>

      {!loaded ? (
        <p className="mt-4 text-sm text-muted">Loading…</p>
      ) : (
        <div className="mt-4 space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <FieldLabel label="Household size">
              <Input
                type="number"
                min={1}
                value={size}
                onChange={(e) => {
                  setSize(Number(e.target.value));
                  setSaved(false);
                }}
              />
            </FieldLabel>
            <FieldLabel label="Weekly budget ($)">
              <Input
                value={budget}
                placeholder="optional"
                onChange={(e) => {
                  setBudget(e.target.value);
                  setSaved(false);
                }}
              />
            </FieldLabel>
          </div>

          <div>
            <FieldLabel label="Meals to plan">
              <div className="mt-1 flex flex-wrap gap-3 text-sm">
                {MEAL_TYPES.map((m) => (
                  <label key={m} className="flex items-center gap-1.5 capitalize">
                    <input
                      type="checkbox"
                      checked={mealTypes.includes(m)}
                      onChange={() => {
                        toggleMeal(m);
                        setSaved(false);
                      }}
                      className="accent-accent"
                    />
                    {m}
                  </label>
                ))}
              </div>
            </FieldLabel>
          </div>

          <div>
            <FieldLabel label="Preferred cuisines">
              <div className="mt-1">
                <CuisineSelector
                  selected={cuisines}
                  onChange={(next) => {
                    setCuisines(next);
                    setSaved(false);
                  }}
                />
              </div>
            </FieldLabel>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FieldLabel label="Dietary flags">
              <Input
                placeholder="e.g. vegetarian, gluten-free"
                value={flags}
                onChange={(e) => {
                  setFlags(e.target.value);
                  setSaved(false);
                }}
              />
            </FieldLabel>
            <FieldLabel label="Avoid / dislikes">
              <Input
                placeholder="e.g. no mushrooms"
                value={avoid}
                onChange={(e) => {
                  setAvoid(e.target.value);
                  setSaved(false);
                }}
              />
            </FieldLabel>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FieldLabel label="Region / ZIP">
              <Input
                placeholder="e.g. 27601"
                value={region}
                onChange={(e) => {
                  setRegion(e.target.value);
                  setSaved(false);
                }}
              />
            </FieldLabel>
            <FieldLabel label="Preferred store">
              <Input
                placeholder="e.g. Harris Teeter"
                value={store}
                onChange={(e) => {
                  setStore(e.target.value);
                  setSaved(false);
                }}
              />
            </FieldLabel>
          </div>

          <div>
            <FieldLabel label="Cooking style">
              <div className="mt-1 flex flex-wrap gap-2">
                {COOKING_TIMES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => {
                      setCookingTime(t.value);
                      setSaved(false);
                    }}
                    className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                      cookingTime === t.value
                        ? "border-accent bg-accent text-white"
                        : "border-line bg-surface text-ink hover:bg-surface-2"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </FieldLabel>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={save} disabled={saving} data-testid="profile-save">
              {saving ? "Saving…" : "Save changes"}
            </Button>
            {saved && <span className="text-sm text-good">✓ Saved</span>}
          </div>
        </div>
      )}
    </Card>
  );
}

function FieldLabel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function Appearance() {
  const { theme, setTheme } = useTheme();

  // Apply locally (instant) and persist to the profile so it follows across
  // devices. Persistence is best-effort — the local change stands regardless.
  const choose = (t: Theme) => {
    setTheme(t);
    void api.setMyTheme(t).catch(() => {});
  };

  return (
    <Card className="p-5">
      <SectionLabel>Appearance</SectionLabel>
      <h3 className="mt-2 font-display text-lg font-semibold">Theme</h3>
      <p className="mt-1 text-sm text-muted">
        Pick the look that suits you. Saved to your account and synced across devices.
      </p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="theme-picker">
        {THEMES.map((t) => (
          <ThemeOption key={t} theme={t} active={t === theme} onSelect={() => choose(t)} />
        ))}
      </div>
    </Card>
  );
}

const SWATCHES: Record<Theme, { bg: string; surface: string; accent: string }> = {
  warm: { bg: "#f6f1e7", surface: "#fffdf8", accent: "#c0532f" },
  fresh: { bg: "#f4f6f4", surface: "#ffffff", accent: "#1f9d6b" },
  dark: { bg: "#16140f", surface: "#211e18", accent: "#d2a24c" },
};

function ThemeOption({
  theme,
  active,
  onSelect,
}: {
  theme: Theme;
  active: boolean;
  onSelect: () => void;
}) {
  const s = SWATCHES[theme];
  return (
    <button
      data-testid={`theme-${theme}`}
      onClick={onSelect}
      className={`rounded-lg border p-3 text-left transition-colors ${
        active ? "border-accent ring-1 ring-accent" : "border-line hover:bg-surface-2"
      }`}
    >
      <div className="flex h-12 items-center gap-1.5 rounded-md px-2" style={{ background: s.bg }}>
        <span
          className="h-6 w-6 rounded-full border"
          style={{ background: s.surface, borderColor: "rgba(0,0,0,0.08)" }}
        />
        <span className="h-6 w-6 rounded-full" style={{ background: s.accent }} />
      </div>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold">{THEME_LABELS[theme]}</span>
        {active && <span className="text-xs font-medium text-accent-ink">Active</span>}
      </div>
    </button>
  );
}
