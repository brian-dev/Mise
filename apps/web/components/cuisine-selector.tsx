"use client";

import { useState } from "react";

import { CUISINE_OPTIONS } from "../lib/cuisines";
import { Button, Input } from "./ui";

/** Curated cuisine chips + an "add your own" field. Controlled: emits the full
 *  selected list on every change. Shared by the onboarding wizard, the Plan form,
 *  and Settings. */
export function CuisineSelector({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [custom, setCustom] = useState("");

  const toggle = (c: string) =>
    onChange(
      selected.some((x) => x.toLowerCase() === c.toLowerCase())
        ? selected.filter((x) => x.toLowerCase() !== c.toLowerCase())
        : [...selected, c],
    );

  const add = () => {
    const c = custom.trim();
    if (c && !selected.some((x) => x.toLowerCase() === c.toLowerCase())) {
      onChange([...selected, c]);
    }
    setCustom("");
  };

  // Selected cuisines outside the curated set still render as (removable) chips.
  const customSelected = selected.filter(
    (c) => !CUISINE_OPTIONS.some((o) => o.toLowerCase() === c.toLowerCase()),
  );

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {CUISINE_OPTIONS.map((c) => (
          <Chip
            key={c}
            label={c}
            active={selected.some((x) => x.toLowerCase() === c.toLowerCase())}
            onClick={() => toggle(c)}
          />
        ))}
        {customSelected.map((c) => (
          <Chip key={c} label={c} active onClick={() => toggle(c)} />
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <Input
          placeholder="Add another cuisine…"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button variant="ghost" onClick={add} disabled={!custom.trim()}>
          Add
        </Button>
      </div>
    </div>
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
