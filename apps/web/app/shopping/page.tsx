"use client";

import Link from "next/link";

import { Button, Card } from "../../components/ui";
import { SectionLabel } from "../shell";
import { useWorkspace } from "../workspace";

export default function ShoppingPage() {
  const { shopping, plan, busy, buildList, estimatePrices, purchase } = useWorkspace();

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

      {shopping.status !== "purchased" && (
        <div className="mt-3 flex flex-wrap gap-2">
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

      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th className="pb-2 font-medium">Item</th>
            <th className="pb-2 font-medium">Qty</th>
            <th className="pb-2 text-right font-medium">Price</th>
          </tr>
        </thead>
        <tbody>
          {shopping.items.map((it) => (
            <tr key={`${it.name}-${it.unit}`} className="border-b border-line/60 last:border-0">
              <td className="py-1.5">{it.name}</td>
              <td className="py-1.5 text-muted">
                {it.quantity_needed} {it.unit}
              </td>
              <td className="py-1.5 text-right">
                {it.estimated_price ? `$${it.estimated_price}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
