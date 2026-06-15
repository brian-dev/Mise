"use client";

import Link from "next/link";
import { useState } from "react";

import type { ShoppingItem } from "../../lib/api";
import { Button, Card, Input } from "../../components/ui";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

export default function ShoppingPage() {
  const {
    shopping,
    plan,
    busy,
    buildList,
    estimatePrices,
    purchase,
    toggleItem,
    addItem,
    removeItem,
  } = useWorkspace();
  const [newItem, setNewItem] = useState("");

  if (!shopping) {
    return (
      <Card className="p-6">
        <SectionLabel>Shopping</SectionLabel>
        <h3 className="mt-2 font-display text-xl font-semibold">No list yet</h3>
        <p className="mt-1 text-sm text-muted">
          {plan
            ? "Build a shopping list from your current plan."
            : "Generate a plan first, then build a shopping list."}
        </p>
        <div className="mt-4">
          {plan ? (
            <Button
              data-testid="build-shopping"
              onClick={() => buildList()}
              disabled={busy === "shopping"}
            >
              {busy === "shopping" ? "Building…" : "Build shopping list"}
            </Button>
          ) : (
            <Link href="/plan">
              <Button>Go to Plan →</Button>
            </Link>
          )}
        </div>
      </Card>
    );
  }

  const hasUnpriced = shopping.items.some((it) => it.estimated_price === null);
  const checkedCount = shopping.items.filter((it) => it.is_checked).length;
  const purchased = shopping.status === "purchased";
  const groups = groupByCategory(shopping.items);

  const onAdd = async () => {
    const name = newItem.trim();
    if (!name) return;
    setNewItem("");
    await addItem(name);
  };

  return (
    <Card className="p-5" data-testid="shopping-list">
      <div className="flex items-center justify-between">
        <SectionLabel>Shopping list · {shopping.status}</SectionLabel>
        <div className="text-sm">
          Total:{" "}
          <strong data-testid="estimated-total" className="font-display text-base">
            ${shopping.estimated_total}
          </strong>
          {hasUnpriced && <em className="text-muted"> (some unpriced)</em>}
        </div>
      </div>

      <p className="mt-1 text-xs text-muted">
        {checkedCount} of {shopping.items.length} checked off
      </p>

      {/* Add manual item */}
      {!purchased && (
        <div className="mt-3 flex gap-2">
          <Input
            data-testid="add-item-input"
            placeholder="Add an item (e.g. milk, paper towels)"
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void onAdd();
              }
            }}
          />
          <Button
            data-testid="add-item"
            variant="ghost"
            onClick={onAdd}
            disabled={!newItem.trim() || busy === "add-item"}
          >
            Add
          </Button>
        </div>
      )}

      {/* Grouped, checkable items */}
      <div className="mt-4 space-y-4">
        {groups.map(([category, items]) => (
          <div key={category}>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              {category}
            </div>
            <ul className="mt-1">
              {items.map((it) => (
                <li
                  key={it.id}
                  data-testid="shopping-item"
                  className="flex items-center gap-3 border-b border-line/60 py-2 last:border-0"
                >
                  <input
                    type="checkbox"
                    checked={it.is_checked}
                    disabled={purchased}
                    onChange={(e) => void toggleItem(it.id, e.target.checked)}
                    className="h-4 w-4 shrink-0 accent-accent"
                    data-testid="item-check"
                  />
                  <span
                    className={`flex-1 text-sm ${
                      it.is_checked ? "text-muted line-through" : ""
                    }`}
                  >
                    {it.name}
                    {it.source === "manual" && (
                      <span className="ml-1.5 text-[10px] uppercase tracking-wide text-muted">
                        added
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs text-muted">
                    {it.quantity_needed} {it.unit}
                  </span>
                  <span className="w-14 shrink-0 text-right text-sm">
                    {it.estimated_price ? `$${it.estimated_price}` : "—"}
                  </span>
                  {!purchased && (
                    <button
                      onClick={() => void removeItem(it.id)}
                      disabled={busy === `remove-${it.id}`}
                      aria-label={`Remove ${it.name}`}
                      data-testid="item-remove"
                      className="shrink-0 text-muted hover:text-accent-ink disabled:opacity-50"
                    >
                      ✕
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {!purchased && (
        <div className="mt-5 flex flex-wrap gap-2">
          {hasUnpriced && (
            <Button
              data-testid="estimate-prices"
              variant="ghost"
              onClick={estimatePrices}
              disabled={busy === "estimate"}
            >
              {busy === "estimate" ? "Estimating…" : "Estimate remaining prices"}
            </Button>
          )}
          <Button data-testid="purchase" onClick={purchase} disabled={busy === "purchase"}>
            {busy === "purchase" ? "Restocking…" : "Mark purchased (restock pantry)"}
          </Button>
        </div>
      )}
    </Card>
  );
}

/** Group items by category (uncategorized last), preserving the server's
 *  within-group ordering. */
function groupByCategory(items: ShoppingItem[]): [string, ShoppingItem[]][] {
  const map = new Map<string, ShoppingItem[]>();
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
