import { useState } from "react";

import type { AppState } from "../../api/types";
import { Button, Card } from "../ui";

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
    <section>
      <button
        onClick={() => setOpen(!open)}
        className="mb-3 text-lg font-bold text-ink"
      >
        Quick Add from Templates{" "}
        <span className="text-muted">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {state.templates.map((template) => {
            const added = existing.has(template.name.toLowerCase());
            return (
              <Card key={template.name} className="flex flex-col gap-2">
                <div>
                  <p className="font-bold">{template.name}</p>
                  <p className="text-xs text-muted">
                    serves {template.servings}
                  </p>
                </div>
                <p className="text-xs text-muted">
                  {template.ingredients.map((i) => i.name).join(", ")}
                </p>
                <div>
                  <Button
                    variant="secondary"
                    disabled={busy || added}
                    onClick={() => onAdd(template.name)}
                  >
                    {added ? "Added" : "Add"}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}
