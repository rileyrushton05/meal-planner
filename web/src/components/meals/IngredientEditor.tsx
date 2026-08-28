import { useState } from "react";

import type { AppState, Meal } from "../../api/types";
import { Button, Card, Field, NumberInput, SectionTitle, Select, TextInput } from "../ui";

export function IngredientEditor({
  state,
  meal,
  busy,
  onSelectMeal,
  onAdd,
  onUpdate,
  onRemove,
}: {
  state: AppState;
  meal: Meal;
  busy: boolean;
  onSelectMeal: (id: number) => void;
  onAdd: (mealId: number, name: string, qty: number, unit: string) => void;
  onUpdate: (
    mealId: number,
    ingredientId: number,
    qty: number,
    unit: string,
  ) => void;
  onRemove: (mealId: number, ingredientId: number) => void;
}) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState("");
  const [unit, setUnit] = useState("");

  const quantity = Number(qty);
  const valid = name.trim().length > 0 && quantity > 0;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    onAdd(meal.id, name.trim(), quantity, unit.trim());
    setName("");
    setQty("");
    setUnit("");
  };

  return (
    <section>
      <SectionTitle>Add Ingredients to a Meal</SectionTitle>
      <Card className="flex flex-col gap-4">
        <Field label="Select meal">
          <Select
            value={meal.id}
            onChange={(e) => onSelectMeal(Number(e.target.value))}
          >
            {state.meals.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </Select>
        </Field>

        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Ingredient">
            {/* A datalist gives native autocomplete over known ingredients
                while still accepting anything typed - the exact behaviour
                the Streamlit searchbox could not manage. */}
            <TextInput
              list="known-ingredients"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Search or type a new one"
            />
            <datalist id="known-ingredients">
              {state.ingredient_names.map((n) => (
                <option key={n} value={n} />
              ))}
            </datalist>
          </Field>
          <div className="w-28">
            <Field label="Quantity">
              <NumberInput
                min={0}
                step="any"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                placeholder="200"
              />
            </Field>
          </div>
          <div className="w-32">
            <Field label="Unit">
              <TextInput
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="g, ml, tbsp"
              />
            </Field>
          </div>
          <Button type="submit" disabled={busy || !valid}>
            Add Ingredient
          </Button>
        </form>

        {meal.ingredients.length === 0 ? (
          <p className="text-sm text-muted">No ingredients added yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {meal.ingredients.map((ingredient) => (
              <IngredientRow
                key={ingredient.ingredient_id}
                mealId={meal.id}
                ingredient={ingredient}
                busy={busy}
                onUpdate={onUpdate}
                onRemove={onRemove}
              />
            ))}
          </div>
        )}
      </Card>
    </section>
  );
}


export function IngredientRow({
  mealId,
  ingredient,
  busy,
  onUpdate,
  onRemove,
}: {
  mealId: number;
  ingredient: AppState["meals"][number]["ingredients"][number];
  busy: boolean;
  onUpdate: (
    mealId: number,
    ingredientId: number,
    qty: number,
    unit: string,
  ) => void;
  onRemove: (mealId: number, ingredientId: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [qty, setQty] = useState(String(ingredient.qty));
  const [unit, setUnit] = useState(ingredient.unit);

  const quantity = Number(qty);

  return (
    <div className="rounded-lg border border-edge bg-canvas px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm">
          {ingredient.name} — {ingredient.qty} {ingredient.unit}
        </span>
        <div className="flex shrink-0 gap-2">
          <Button variant="secondary" onClick={() => setEditing(!editing)}>
            Edit
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => onRemove(mealId, ingredient.ingredient_id)}
          >
            Remove
          </Button>
        </div>
      </div>

      {editing && (
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <div className="w-28">
            <Field label="Quantity">
              <NumberInput
                min={0}
                step="any"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </Field>
          </div>
          <div className="w-32">
            <Field label="Unit">
              <TextInput
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
            </Field>
          </div>
          <Button
            disabled={busy || !(quantity > 0)}
            onClick={() => {
              onUpdate(mealId, ingredient.ingredient_id, quantity, unit.trim());
              setEditing(false);
            }}
          >
            Save
          </Button>
        </div>
      )}
    </div>
  );
}
