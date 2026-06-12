"use client";

import { useState } from "react";

import { MEAL_TYPES, type MealType } from "@mise/shared";

import { api, type ConsentDecision, type OnboardingStatus } from "../../lib/api";
import { Button, Input } from "../../components/ui";
import { CuisineSelector } from "../../components/cuisine-selector";

// Bump when the consent copy materially changes; stored with each ledger row.
const CONSENT_VERSION = "2026-06-12";

const COOKING_TIMES = [
  { value: "quick", label: "Quick & easy", hint: "30 minutes or less, minimal fuss" },
  { value: "standard", label: "Balanced", hint: "Typical weeknight cooking" },
  { value: "elaborate", label: "I love to cook", hint: "Happy to spend time in the kitchen" },
];

interface Data {
  name: string;
  household_size: number;
  preferred_cuisines: string[];
  preferred_meal_types: MealType[];
  weekly_budget: string;
  dietary_flags: string[];
  avoid_text: string;
  region: string;
  store_preference: string;
  cooking_time: string;
  consents: {
    personalization: boolean;
    analytics: boolean;
    data_sharing: boolean;
    marketing: boolean;
  };
}

const INITIAL: Data = {
  name: "",
  household_size: 2,
  preferred_cuisines: [],
  preferred_meal_types: ["dinner"],
  weekly_budget: "",
  dietary_flags: [],
  avoid_text: "",
  region: "",
  store_preference: "",
  cooking_time: "standard",
  consents: {
    personalization: true,
    analytics: true,
    data_sharing: false,
    marketing: false,
  },
};

const DIETARY = [
  "Vegetarian",
  "Vegan",
  "Pescatarian",
  "Gluten-free",
  "Dairy-free",
  "Nut-free",
  "Halal",
  "Kosher",
];

export function OnboardingWizard({ status }: { status: OnboardingStatus }) {
  const [data, setData] = useState<Data>(INITIAL);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Data>(key: K, value: Data[K]) =>
    setData((d) => ({ ...d, [key]: value }));

  const steps = buildSteps(data, set);
  const current = steps[step]!;
  const isLast = step === steps.length - 1;

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      let householdId = status.household_id;
      if (!householdId) {
        const h = await api.createHousehold(data.name.trim() || "My Household");
        householdId = h.id;
      }
      await api.putProfile(householdId, {
        household_size: data.household_size,
        weekly_budget: data.weekly_budget ? data.weekly_budget : null,
        preferred_cuisines: data.preferred_cuisines,
        preferred_meal_types: data.preferred_meal_types,
        cooking_time: data.cooking_time,
        dietary_flags: data.dietary_flags,
        avoid_text: data.avoid_text || null,
        region: data.region || null,
        store_preference: data.store_preference || null,
        complete_onboarding: true,
      });
      const decisions: ConsentDecision[] = Object.entries(data.consents).map(
        ([kind, granted]) => ({ kind, granted }),
      );
      await api.postConsents(CONSENT_VERSION, decisions);
      await api.logEvent("onboarding_finished", householdId, {}).catch(() => {});
      // Reload so the workspace picks up the new household + the gate clears.
      window.location.assign("/");
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-bg">
      <div className="mx-auto flex min-h-screen max-w-xl flex-col px-5 py-7">
        {/* Header — onboarding is required, so there's no skip. */}
        <div className="flex items-center">
          <span className="font-display text-xl font-semibold tracking-tight">
            Mise<span className="text-accent">.</span>
          </span>
        </div>

        {/* Progress */}
        <div className="mt-5 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full rounded-full bg-accent transition-all duration-300"
            style={{ width: `${((step + 1) / steps.length) * 100}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-muted">
          Step {step + 1} of {steps.length}
        </p>

        {/* Body */}
        <div className="mt-6 flex-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            {current.title}
          </h1>
          {current.subtitle && (
            <p className="mt-1 text-sm text-muted">{current.subtitle}</p>
          )}
          <div className="mt-5">{current.body}</div>
          {error && (
            <div className="mt-4 rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || busy}
          >
            Back
          </Button>
          {isLast ? (
            <Button onClick={() => finish()} disabled={busy} data-testid="onboarding-finish">
              {busy ? "Setting up…" : "Finish"}
            </Button>
          ) : (
            <Button
              onClick={() => setStep((s) => s + 1)}
              disabled={busy || !current.canNext}
              data-testid="onboarding-next"
            >
              Continue
            </Button>
          )}
        </div>
      </div>
    </main>
  );
}

interface Step {
  title: string;
  subtitle?: string;
  body: React.ReactNode;
  canNext: boolean;
}

function buildSteps(
  data: Data,
  set: <K extends keyof Data>(key: K, value: Data[K]) => void,
): Step[] {
  const toggle = <T,>(list: T[], v: T): T[] =>
    list.some((x) => String(x).toLowerCase() === String(v).toLowerCase())
      ? list.filter((x) => String(x).toLowerCase() !== String(v).toLowerCase())
      : [...list, v];

  return [
    {
      title: "Welcome to Mise",
      subtitle: "A few quick questions so every plan starts tailored to you. Takes under a minute.",
      canNext: data.name.trim().length > 0,
      body: (
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            What should we call this household?
          </span>
          <Input
            className="mt-1"
            placeholder="e.g. Home"
            value={data.name}
            onChange={(e) => set("name", e.target.value)}
            autoFocus
          />
        </label>
      ),
    },
    {
      title: "How many are you cooking for?",
      subtitle: "We scale recipes to this by default.",
      canNext: true,
      body: <Stepper value={data.household_size} onChange={(v) => set("household_size", v)} />,
    },
    {
      title: "Which cuisines do you love?",
      subtitle: "Plans will lean toward these. Add as many as you like — or skip and decide later.",
      canNext: true,
      body: (
        <CuisineSelector
          selected={data.preferred_cuisines}
          onChange={(next) => set("preferred_cuisines", next)}
        />
      ),
    },
    {
      title: "What should we plan, and what's your budget?",
      subtitle: "Pick the meals you want planned and a rough weekly grocery budget.",
      canNext: data.preferred_meal_types.length > 0,
      body: (
        <div className="space-y-5">
          <div>
            <Label>Meals to plan</Label>
            <div className="mt-2 flex flex-wrap gap-2">
              {MEAL_TYPES.map((m) => (
                <Chip
                  key={m}
                  label={cap(m)}
                  active={data.preferred_meal_types.includes(m)}
                  onClick={() => set("preferred_meal_types", toggle(data.preferred_meal_types, m))}
                />
              ))}
            </div>
          </div>
          <label className="block">
            <Label>Weekly grocery budget (optional)</Label>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-muted">$</span>
              <Input
                type="number"
                inputMode="decimal"
                placeholder="e.g. 120"
                value={data.weekly_budget}
                onChange={(e) => set("weekly_budget", e.target.value)}
              />
            </div>
          </label>
        </div>
      ),
    },
    {
      title: "Any dietary needs?",
      subtitle: "We treat these as hard rules. Add anything to avoid below.",
      canNext: true,
      body: (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            {DIETARY.map((d) => (
              <Chip
                key={d}
                label={d}
                active={data.dietary_flags.some((x) => x.toLowerCase() === d.toLowerCase())}
                onClick={() => set("dietary_flags", toggle(data.dietary_flags, d))}
              />
            ))}
          </div>
          <label className="block">
            <Label>Foods to avoid / dislikes (optional)</Label>
            <Input
              className="mt-1"
              placeholder="e.g. no mushrooms, no shellfish, kids dislike spicy"
              value={data.avoid_text}
              onChange={(e) => set("avoid_text", e.target.value)}
            />
          </label>
        </div>
      ),
    },
    {
      title: "Where do you shop?",
      subtitle: "Used to estimate grocery prices in your area. We never share your exact address.",
      canNext: true,
      body: (
        <div className="space-y-4">
          <label className="block">
            <Label>Region / ZIP (optional)</Label>
            <Input
              className="mt-1"
              placeholder="e.g. 27601 or Raleigh, NC"
              value={data.region}
              onChange={(e) => set("region", e.target.value)}
            />
          </label>
          <label className="block">
            <Label>Preferred store (optional)</Label>
            <Input
              className="mt-1"
              placeholder="e.g. Harris Teeter"
              value={data.store_preference}
              onChange={(e) => set("store_preference", e.target.value)}
            />
          </label>
        </div>
      ),
    },
    {
      title: "How much time do you like to spend cooking?",
      canNext: true,
      body: (
        <div className="space-y-2">
          {COOKING_TIMES.map((t) => (
            <button
              key={t.value}
              onClick={() => set("cooking_time", t.value)}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${
                data.cooking_time === t.value
                  ? "border-accent ring-1 ring-accent"
                  : "border-line hover:bg-surface-2"
              }`}
            >
              <div className="font-semibold">{t.label}</div>
              <div className="text-sm text-muted">{t.hint}</div>
            </button>
          ))}
        </div>
      ),
    },
    {
      title: "Your privacy choices",
      subtitle: "You're in control. Change any of these anytime in Settings.",
      canNext: data.consents.personalization,
      body: (
        <div className="space-y-3">
          <ConsentRow
            checked={data.consents.personalization}
            onChange={(v) => set("consents", { ...data.consents, personalization: v })}
            title="Personalize my meal plans"
            desc="Use my preferences to tailor plans. Core to how Mise works — required to use the app."
          />
          <ConsentRow
            checked={data.consents.analytics}
            onChange={(v) => set("consents", { ...data.consents, analytics: v })}
            title="Help improve Mise"
            desc="Use my data in aggregated, anonymized form to improve the product."
          />
          <ConsentRow
            checked={data.consents.data_sharing}
            onChange={(v) => set("consents", { ...data.consents, data_sharing: v })}
            title="Share anonymized insights with partners"
            desc="Allow aggregated, anonymized data to be shared with trusted partners (e.g. grocers). Never your personal details."
          />
          <ConsentRow
            checked={data.consents.marketing}
            onChange={(v) => set("consents", { ...data.consents, marketing: v })}
            title="Send me product emails"
            desc="Occasional tips and product updates. No spam."
          />
        </div>
      ),
    },
  ];
}

// --- small building blocks --------------------------------------------------

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
      {children}
    </span>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "border-accent bg-accent text-white"
          : "border-line bg-surface text-ink hover:bg-surface-2"
      }`}
    >
      {label}
    </button>
  );
}

function Stepper({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-4">
      <button
        onClick={() => onChange(Math.max(1, value - 1))}
        className="grid h-10 w-10 place-items-center rounded-full border border-line text-lg hover:bg-surface-2"
        aria-label="Decrease"
      >
        −
      </button>
      <span className="w-10 text-center font-display text-2xl font-semibold">{value}</span>
      <button
        onClick={() => onChange(value + 1)}
        className="grid h-10 w-10 place-items-center rounded-full border border-line text-lg hover:bg-surface-2"
        aria-label="Increase"
      >
        +
      </button>
    </div>
  );
}

function ConsentRow({
  checked,
  onChange,
  title,
  desc,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  desc: string;
}) {
  return (
    <label className="flex cursor-pointer gap-3 rounded-lg border border-line p-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-accent"
      />
      <span>
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-xs text-muted">{desc}</span>
      </span>
    </label>
  );
}
