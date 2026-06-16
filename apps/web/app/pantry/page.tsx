"use client";

import { useState } from "react";

import { UNITS } from "@mise/shared";

import type { PantryItem } from "../../lib/api";
import { Button, Card, Input } from "../../components/ui";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

export default function PantryPage() {
  const {
    householdId,
    pantry,
    busy,
    addBarcode,
    addPantryItem,
    updatePantryItem,
    removePantryItem,
  } = useWorkspace();

  const [barcode, setBarcode] = useState("");
  const [name, setName] = useState("");
  const [qty, setQty] = useState("1");
  const [unit, setUnit] = useState("unit");

  if (!householdId) {
    return (
      <Card className="p-6">
        <SectionLabel>Pantry</SectionLabel>
        <p className="mt-2 text-sm text-muted">Select a household to see its pantry.</p>
      </Card>
    );
  }

  const onAddManual = async () => {
    if (!name.trim()) return;
    await addPantryItem(name, Number(qty) || 1, unit);
    setName("");
    setQty("1");
  };

  const onAddBarcode = async () => {
    await addBarcode(barcode);
    setBarcode("");
  };

  const groups = groupByCategory(pantry);

  return (
    <div className="space-y-4">
      {/* Add item */}
      <Card className="p-5">
        <SectionLabel>Add to pantry</SectionLabel>
        <div className="mt-3 flex flex-wrap gap-2">
          <Input
            data-testid="pantry-name"
            placeholder="Item (e.g. olive oil)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void onAddManual();
              }
            }}
            className="min-w-[8rem] flex-1"
          />
          <Input
            data-testid="pantry-qty"
            type="number"
            min={0}
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-20"
          />
          <select
            data-testid="pantry-unit"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="rounded border border-line bg-surface px-2 text-sm text-ink"
          >
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
          <Button
            data-testid="pantry-add"
            onClick={onAddManual}
            disabled={busy === "pantry-add" || !name.trim()}
          >
            {busy === "pantry-add" ? "Adding…" : "Add"}
          </Button>
        </div>

        <div className="mt-3 flex gap-2">
          <Input
            data-testid="barcode-input"
            placeholder="…or scan a barcode (e.g. 3017620422003)"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
          />
          <Button
            data-testid="barcode-add"
            variant="ghost"
            onClick={onAddBarcode}
            disabled={busy === "barcode" || !barcode.trim()}
          >
            {busy === "barcode" ? "Adding…" : "Add by barcode"}
          </Button>
        </div>
      </Card>

      {/* Pantry list */}
      <Card className="p-5">
        <SectionLabel>Pantry · {pantry.length} items</SectionLabel>
        {pantry.length === 0 ? (
          <p className="mt-2 text-sm text-muted">Your pantry is empty.</p>
        ) : (
          <div className="mt-3 space-y-4">
            {groups.map(([category, items]) => (
              <div key={category}>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {category}
                </div>
                <ul className="mt-1">
                  {items.map((p) => (
                    <PantryRow
                      key={p.id}
                      item={p}
                      busy={busy === `pantry-${p.id}`}
                      onUpdate={(q) => updatePantryItem(p.id, q)}
                      onRemove={() => removePantryItem(p.id)}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function PantryRow({
  item,
  busy,
  onUpdate,
  onRemove,
}: {
  item: PantryItem;
  busy: boolean;
  onUpdate: (quantity: number) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(item.quantity);

  const commit = () => {
    setEditing(false);
    const q = Number(value);
    if (!Number.isNaN(q) && String(q) !== String(Number(item.quantity))) onUpdate(q);
  };

  return (
    <li
      data-testid="pantry-item"
      className="flex items-center gap-3 border-b border-line/60 py-2 last:border-0"
    >
      <span className="flex-1 text-sm font-medium">{item.name}</span>
      {editing ? (
        <input
          autoFocus
          type="number"
          min={0}
          step="any"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }}
          className="w-20 rounded border border-line bg-surface px-2 py-0.5 text-sm text-ink"
          data-testid="pantry-qty-edit"
        />
      ) : (
        <button
          onClick={() => {
            setValue(item.quantity);
            setEditing(true);
          }}
          className="text-sm text-muted hover:text-ink"
          data-testid="pantry-qty-display"
        >
          {item.quantity} {item.unit}
        </button>
      )}
      <button
        onClick={onRemove}
        disabled={busy}
        aria-label={`Remove ${item.name}`}
        data-testid="pantry-remove"
        className="shrink-0 text-muted hover:text-accent-ink disabled:opacity-50"
      >
        ✕
      </button>
    </li>
  );
}

function groupByCategory(items: PantryItem[]): [string, PantryItem[]][] {
  const map = new Map<string, PantryItem[]>();
  for (const it of items) {
    const key = it.category ?? "other";
    (map.get(key) ?? map.set(key, []).get(key)!).push(it);
  }
  return [...map.entries()].sort(([a], [b]) => {
    if (a === "other") return 1;
    if (b === "other") return -1;
    return a.localeCompare(b);
  });
}
