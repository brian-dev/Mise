"use client";

import { useState } from "react";

import { Button, Card, Input } from "../../components/ui";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

export default function PantryPage() {
  const { householdId, pantry, busy, addBarcode } = useWorkspace();
  const [barcode, setBarcode] = useState("");

  if (!householdId) {
    return (
      <Card className="p-6">
        <SectionLabel>Pantry</SectionLabel>
        <p className="mt-2 text-sm text-muted">Select a household to see its pantry.</p>
      </Card>
    );
  }

  const onAdd = async () => {
    await addBarcode(barcode);
    setBarcode("");
  };

  return (
    <Card className="p-5">
      <SectionLabel>Pantry</SectionLabel>

      {pantry.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Your pantry is empty.</p>
      ) : (
        <ul className="mt-3 space-y-1.5 text-sm">
          {pantry.map((p) => (
            <li
              key={`${p.name}-${p.unit}`}
              className="flex justify-between border-b border-line/60 py-1.5 last:border-0"
            >
              <span className="font-medium">{p.name}</span>
              <span className="text-muted">
                {p.quantity} {p.unit}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-5">
        <SectionLabel>Add by barcode</SectionLabel>
        <div className="mt-2 flex gap-2">
          <Input
            data-testid="barcode-input"
            placeholder="barcode (e.g. 3017620422003)"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
          />
          <Button
            data-testid="barcode-add"
            onClick={onAdd}
            disabled={busy === "barcode" || !barcode.trim()}
          >
            {busy === "barcode" ? "Adding…" : "Add"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
