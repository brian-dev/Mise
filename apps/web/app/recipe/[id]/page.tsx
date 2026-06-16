"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, type RecipeDetail } from "../../../lib/api";
import { Button, Card } from "../../../components/ui";
import { SectionLabel } from "../../shell";

export default function RecipePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favorite, setFavorite] = useState(false);
  const [note, setNote] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api
      .getRecipe(id)
      .then((r) => {
        setRecipe(r);
        setFavorite(r.is_favorite);
        setNote(r.note ?? "");
        setSavedNote(r.note ?? "");
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  const toggleFavorite = () => {
    const next = !favorite;
    setFavorite(next); // optimistic
    void api.setFavorite(id, next).catch(() => setFavorite(!next));
  };

  const saveNote = async () => {
    setSavingNote(true);
    try {
      await api.saveRecipeNote(id, note);
      setSavedNote(note);
    } finally {
      setSavingNote(false);
    }
  };

  if (loading) return <p className="text-muted">Loading…</p>;
  if (error)
    return (
      <div className="rounded border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent-ink">
        {error}
      </div>
    );
  if (!recipe) return null;

  const totalTime = (recipe.prep_time ?? 0) + (recipe.cook_time ?? 0);
  const steps = (recipe.instructions ?? "")
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <article className="space-y-4">
      <Link href="/plan" className="text-sm font-medium text-muted hover:text-ink">
        ← Back to plan
      </Link>

      {recipe.image_url && (
        // Representative stock photo (Pexels), not an exact render of the dish.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={recipe.image_url}
          alt={recipe.title}
          className="h-56 w-full rounded-lg border border-line object-cover"
        />
      )}

      <div>
        <div className="flex items-start justify-between gap-3">
          <h1 className="font-display text-3xl font-semibold tracking-tight">{recipe.title}</h1>
          <button
            onClick={toggleFavorite}
            aria-label={favorite ? "Remove from favorites" : "Add to favorites"}
            aria-pressed={favorite}
            data-testid="favorite-toggle"
            className={`shrink-0 text-2xl leading-none transition-colors ${
              favorite ? "text-accent" : "text-muted hover:text-accent-ink"
            }`}
          >
            {favorite ? "♥" : "♡"}
          </button>
        </div>
        {recipe.description && (
          <p className="mt-1.5 text-muted">{recipe.description}</p>
        )}
        <p className="mt-2 text-sm text-muted">
          {recipe.cuisine_tags.length > 0 && (
            <span className="capitalize">{recipe.cuisine_tags.join(" · ")}</span>
          )}
          {recipe.cuisine_tags.length > 0 && totalTime > 0 && " · "}
          {totalTime > 0 && `${totalTime} min`}
          {` · serves ${recipe.default_servings}`}
        </p>
      </div>

      <Card className="p-5">
        <SectionLabel>Ingredients</SectionLabel>
        <ul className="mt-3 space-y-1.5 text-sm">
          {recipe.ingredients.map((ing) => (
            <li
              key={`${ing.name}-${ing.unit}`}
              className="flex justify-between border-b border-line/60 py-1.5 last:border-0"
            >
              <span>
                {ing.name}
                {ing.is_optional && (
                  <span className="ml-1.5 text-xs text-muted">(optional)</span>
                )}
              </span>
              <span className="text-muted">
                {ing.quantity} {ing.unit}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      {steps.length > 0 && (
        <Card className="p-5">
          <SectionLabel>Method</SectionLabel>
          <ol className="mt-3 space-y-3 text-sm">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink">
                  {i + 1}
                </span>
                <span className="pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      <Card className="p-5">
        <SectionLabel>My notes</SectionLabel>
        <p className="mt-1 text-xs text-muted">
          Private to you — tweaks, swaps, what worked last time.
        </p>
        <textarea
          data-testid="recipe-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. used half the chili, added lime at the end"
          rows={3}
          className="mt-2 w-full resize-y rounded border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted outline-none focus:border-accent"
        />
        <div className="mt-2 flex items-center gap-3">
          <Button
            data-testid="save-note"
            onClick={saveNote}
            disabled={savingNote || note === savedNote}
          >
            {savingNote ? "Saving…" : "Save note"}
          </Button>
          {note === savedNote && savedNote !== "" && (
            <span className="text-sm text-good">✓ Saved</span>
          )}
        </div>
      </Card>
    </article>
  );
}
