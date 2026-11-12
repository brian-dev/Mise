"use client";

import { useCallback, useState, type ReactNode } from "react";

import { api, type CookPreview, type CookPreviewItem } from "../lib/api";
import { Button, Dialog } from "./ui";

type DoCook = (mealId: string, overrides?: Record<string, number>) => Promise<void>;

/**
 * Partial-use prompt at cook time (PRODUCT_SPEC §3.4). `start(mealId)` asks the
 * API what cooking would deduct; when nothing needs a judgement call it cooks
 * straight away (one tap, as before), otherwise it opens a dialog to confirm the
 * flagged amounts and cooks with those as overrides. Render `dialog` somewhere
 * in the page.
 */
export function useCookFlow(doCook: DoCook): {
  start: (mealId: string) => Promise<void>;
  checking: string | null;
  dialog: ReactNode;
} {
  const [preview, setPreview] = useState<CookPreview | null>(null);
  const [checking, setChecking] = useState<string | null>(null);

  const start = useCallback(
    async (mealId: string) => {
      setChecking(mealId);
      let p: CookPreview | null = null;
      try {
        p = await api.cookPreview(mealId);
      } catch {
        // The prompt is a nicety — if the preview fails, cook as before.
      } finally {
        setChecking(null);
      }
      if (p?.needs_confirm) setPreview(p);
      else await doCook(mealId);
    },
    [doCook],
  );

  const close = useCallback(() => setPreview(null), []);

  const dialog = preview ? (
    <CookDialog
      preview={preview}
      onCancel={close}
      onConfirm={async (overrides) => {
        const id = preview.meal_id;
        setPreview(null);
        await doCook(id, overrides);
      }}
    />
  ) : null;

  return { start, checking, dialog };
}

function CookDialog({
  preview,
  onCancel,
  onConfirm,
}: {
  preview: CookPreview;
  onCancel: () => void;
  onConfirm: (overrides: Record<string, number>) => void;
}) {
  const deductible = preview.ingredients.filter((i) => i.on_hand !== null);
  const flagged = deductible.filter((i) => i.reason);
  const others = deductible.filter((i) => !i.reason);

  const [showAll, setShowAll] = useState(false);
  const [amounts, setAmounts] = useState<Record<string, string>>(() =>
    Object.fromEntries(deductible.map((i) => [i.ingredient_id, trim(i.planned)])),
  );
  const set = (id: string, v: string) => setAmounts((a) => ({ ...a, [id]: v }));

  const shown = showAll ? [...flagged, ...others] : flagged;
  const values = shown.map((i) => Number(amounts[i.ingredient_id]));
  const valid = values.every((v) => Number.isFinite(v) && v >= 0);

  const confirm = () => {
    const overrides: Record<string, number> = {};
    for (const i of shown) overrides[i.ingredient_id] = Number(amounts[i.ingredient_id]);
    onConfirm(overrides);
  };

  return (
    <Dialog title="How much did you use?" onClose={onCancel} data-testid="cook-dialog">
      <p className="text-sm text-muted">
        {flagged.length === 1
          ? "One amount is a judgement call"
          : `${flagged.length} amounts are a judgement call`}{" "}
        — adjust so your pantry stays accurate.
      </p>

      <ul className="mt-4 space-y-4">
        {shown.map((i) => (
          <AmountRow
            key={i.ingredient_id}
            item={i}
            value={amounts[i.ingredient_id] ?? ""}
            onChange={(v) => set(i.ingredient_id, v)}
          />
        ))}
      </ul>

      {others.length > 0 && (
        <button
          type="button"
          data-testid="cook-dialog-show-all"
          onClick={() => setShowAll((s) => !s)}
          className="mt-4 text-sm font-medium text-muted hover:text-ink"
        >
          {showAll
            ? "Only show the ones to check ▴"
            : `Adjust the other ${others.length} ingredient${others.length === 1 ? "" : "s"} ▾`}
        </button>
      )}

      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel} data-testid="cook-dialog-cancel">
          Cancel
        </Button>
        <Button onClick={confirm} disabled={!valid} data-testid="cook-dialog-confirm">
          Mark cooked
        </Button>
      </div>
    </Dialog>
  );
}

function AmountRow({
  item,
  value,
  onChange,
}: {
  item: CookPreviewItem;
  value: string;
  onChange: (v: string) => void;
}) {
  const planned = Number(item.planned);
  const onHand = Number(item.on_hand);
  const hint =
    item.reason === "short"
      ? `Recipe calls for ${qty(planned, item.unit)} — you had ${qty(onHand, item.unit)}.`
      : item.reason === "partial"
        ? `Recipe calls for ${qty(planned, item.unit)} (${qty(onHand, item.unit)} on hand).`
        : `${qty(onHand, item.unit)} on hand.`;

  // One-tap answers for the usual cases.
  const quick: { label: string; value: number }[] = [];
  if (item.reason === "partial") {
    quick.push({ label: `Just ${qty(planned, item.unit)}`, value: planned });
    const whole = Math.min(Math.ceil(planned), onHand);
    if (whole > planned) quick.push({ label: `Used ${qty(whole, item.unit)}`, value: whole });
  }
  if (item.reason === "short") quick.push({ label: "Used all I had", value: onHand });

  return (
    <li data-testid="cook-dialog-item" data-reason={item.reason ?? ""}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium">{item.name}</span>
        <span className="flex items-center gap-1.5">
          <input
            type="number"
            min={0}
            step="any"
            inputMode="decimal"
            aria-label={`Amount of ${item.name} used`}
            data-testid="cook-dialog-amount"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="w-20 rounded border border-line bg-surface px-2 py-1 text-right text-sm text-ink outline-none focus:border-accent"
          />
          <span className="w-12 text-sm text-muted">{unitLabel(item.unit, Number(value))}</span>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted">{hint}</p>
      {quick.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {quick.map((q) => (
            <button
              key={q.label}
              type="button"
              onClick={() => onChange(trim(String(q.value)))}
              className="rounded-full border border-line px-2.5 py-0.5 text-xs font-medium text-ink hover:bg-surface-2"
            >
              {q.label}
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

// ---- formatting ------------------------------------------------------------ //
const COUNT_PLURALS: Record<string, string> = {
  can: "cans",
  bunch: "bunches",
  clove: "cloves",
  slice: "slices",
  pinch: "pinches",
  cup: "cups",
};

function unitLabel(unit: string, amount: number): string {
  const one = amount > 0 && amount <= 1; // "½ can", "1 can", "2 cans"
  if (unit === "unit") return one ? "item" : "items";
  if (unit === "fl_oz") return "fl oz";
  return one ? unit : (COUNT_PLURALS[unit] ?? unit);
}

const FRACTIONS: Record<string, string> = { "0.25": "¼", "0.5": "½", "0.75": "¾" };

function qty(amount: number, unit: string): string {
  const whole = Math.floor(amount);
  const frac = trim(String(+(amount - whole).toFixed(3)));
  const nice =
    frac in FRACTIONS ? `${whole ? whole : ""}${FRACTIONS[frac]}` : trim(String(+amount.toFixed(2)));
  return `${nice} ${unitLabel(unit, amount)}`;
}

function trim(s: string): string {
  return String(Number(s));
}
