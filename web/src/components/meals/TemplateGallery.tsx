import { ChevronDown, Plus } from "lucide-react";
import { useState } from "react";

import type { AppState } from "@/api/types";

export function TemplateGallery({
  state,
  busy,
  onAdd,
}: {
  state: AppState;
  busy: boolean;
  onAdd: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const existing = new Set(state.meals.map((m) => m.name.toLowerCase()));

  return (
    <section className="rounded-xl border bg-card">
      {/* A full-width row rather than a bare heading: the whole strip is the
          hit target, so there is no small "+" to aim at. */}
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-5 py-4 text-left transition-colors hover:bg-accent/50"
      >
        <span>
          <span className="font-medium">Quick add from templates</span>
          <span className="ml-2 text-sm text-muted-foreground">
            {state.templates.length} common meals, ingredients included
          </span>
        </span>
        <ChevronDown
          className={`size-4 shrink-0 text-muted-foreground transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open && (
        <div className="grid gap-2 border-t p-3 sm:grid-cols-2 lg:grid-cols-3">
          {state.templates.map((template) => {
            const added = existing.has(template.name.toLowerCase());
            return (
              <button
                key={template.name}
                disabled={busy || added}
                onClick={() => onAdd(template.name)}
                aria-label={added ? `${template.name} (added)` : `Add ${template.name}`}
                className="group flex items-start justify-between gap-3 rounded-lg border p-3 text-left transition-colors hover:border-primary/50 hover:bg-accent/40 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border disabled:hover:bg-transparent"
              >
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{template.name}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                    {template.ingredients.map((i) => i.name).join(", ")}
                  </span>
                </span>
                <span className="mt-0.5 shrink-0 text-xs text-muted-foreground">
                  {added ? "Added" : <Plus className="size-4" />}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
