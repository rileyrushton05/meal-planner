import { useState } from "react";

import type { Meal } from "../../api/types";
import { Button, Card, Field, NumberInput, TextInput } from "../ui";

export function MealRow({
  meal,
  busy,
  onUpdate,
  onDelete,
}: {
  meal: Meal;
  busy: boolean;
  onUpdate: (id: number, name: string, servings: number) => void;
  onDelete: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [name, setName] = useState(meal.name);
  const [servings, setServings] = useState(String(meal.servings));

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-bold">{meal.name}</p>
          <p className="text-xs text-muted">
            serves {meal.servings} · {meal.ingredients.length} ingredient
            {meal.ingredients.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="secondary" onClick={() => setEditing(!editing)}>
            Edit
          </Button>
          <Button variant="secondary" onClick={() => setConfirming(true)}>
            Delete
          </Button>
        </div>
      </div>

      {confirming && (
        <div
          role="alertdialog"
          aria-label={`Confirm deleting ${meal.name}`}
          className="mt-3 rounded-lg border border-edge bg-canvas p-3"
        >
          <p className="mb-3 text-sm">
            Delete <strong>{meal.name}</strong>? This also removes its
            ingredients and unassigns it from any planned day.
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={busy}
              onClick={() => {
                setConfirming(false);
                onDelete(meal.id);
              }}
            >
              Yes, delete
            </Button>
          </div>
        </div>
      )}

      {editing && (
        <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-edge pt-3">
          <Field label="Meal name">
            <TextInput value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="w-28">
            <Field label="Servings">
              <NumberInput
                min={1}
                value={servings}
                onChange={(e) => setServings(e.target.value)}
              />
            </Field>
          </div>
          <Button
            disabled={busy || !name.trim()}
            onClick={() => {
              onUpdate(meal.id, name.trim(), Math.max(1, Number(servings) || 1));
              setEditing(false);
            }}
          >
            Save
          </Button>
        </div>
      )}
    </Card>
  );
}
