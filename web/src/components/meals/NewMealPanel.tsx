import { ArrowRight, Plus, Search } from "lucide-react";
import { useState } from "react";

import type { AppState } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { BackToList } from "./MealPanel";

/**
 * Starting a meal: a name and servings, then straight on to its ingredients
 * (the page opens the new meal with the cursor in the ingredient field). Or
 * skip the typing and start from a template, which comes with ingredients.
 */
export function NewMealPanel({
  state,
  pending,
  onBack,
  onCreate,
  onCreateFromTemplate,
}: {
  state: AppState;
  pending: boolean;
  onBack?: () => void;
  onCreate: (name: string, servings: number) => void;
  onCreateFromTemplate: (name: string) => void;
}) {
  const [name, setName] = useState("");
  // Held as text so the field can be cleared while typing a new number.
  const [servings, setServings] = useState("4");
  const [query, setQuery] = useState("");

  const existing = new Set(state.meals.map((m) => m.name.toLowerCase()));
  const needle = query.trim().toLowerCase();
  const templates = needle
    ? state.templates.filter(
        (t) =>
          t.name.toLowerCase().includes(needle) ||
          t.ingredients.some((i) => i.name.toLowerCase().includes(needle)),
      )
    : state.templates;

  return (
    <section aria-labelledby="new-meal-title" className="rounded-xl border bg-card">
      <BackToList onBack={onBack} />

      <header className="border-b p-4 sm:p-5">
        <h2 id="new-meal-title" className="font-heading text-xl font-semibold">
          New meal
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Name it, and you'll go straight on to its ingredients.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) onCreate(name.trim(), Math.max(1, Number(servings) || 1));
        }}
        className="flex flex-wrap items-end gap-3 p-4 sm:p-5"
      >
        <div className="min-w-48 flex-1 space-y-1.5">
          <Label htmlFor="meal-name">Meal name</Label>
          <Input
            id="meal-name"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Spaghetti Bolognese"
          />
        </div>
        <div className="w-24 space-y-1.5">
          <Label htmlFor="meal-servings">Servings</Label>
          <Input
            id="meal-servings"
            type="number"
            min={1}
            value={servings}
            onChange={(e) => setServings(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={pending || !name.trim()}>
          Create meal
          <ArrowRight aria-hidden />
        </Button>
      </form>

      <div className="border-t p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
              Or start from a template
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {state.templates.length} common meals, ingredients included.
            </p>
          </div>
          <div className="relative w-full sm:w-56">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              aria-label="Search templates"
              placeholder="Search templates"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-8"
            />
          </div>
        </div>

        {/* grid-cols-1 rather than an implicit column, which grows to its
            longest line and pushed a phone-width panel off screen. */}
        {templates.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No templates match “{query.trim()}”.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {templates.map((template) => {
              const added = existing.has(template.name.toLowerCase());
              return (
                <li key={template.name}>
                  <button
                    type="button"
                    disabled={pending || added}
                    onClick={() => onCreateFromTemplate(template.name)}
                    aria-label={added ? `${template.name} (added)` : `Add ${template.name}`}
                    className="flex w-full items-start justify-between gap-3 rounded-lg border p-3 text-left outline-none transition-colors hover:border-primary/50 hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border disabled:hover:bg-transparent"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{template.name}</span>
                      <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                        {template.ingredients.map((i) => i.name).join(", ")}
                      </span>
                    </span>
                    <span className="mt-0.5 shrink-0 text-xs text-muted-foreground">
                      {added ? "Added" : <Plus aria-hidden className="size-4" />}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
