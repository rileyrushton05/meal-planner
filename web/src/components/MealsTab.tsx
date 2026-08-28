import { useState } from "react";

import type { AppState, Meal } from "../api/types";
import {
  Button,
  Card,
  Empty,
  Field,
  NumberInput,
  SectionTitle,
  Select,
  TextInput,
} from "./ui";

interface Props {
  state: AppState;
  busy: boolean;
  onAddMeal: (name: string, servings: number) => void;
  onAddFromTemplate: (name: string) => void;
  onUpdateMeal: (id: number, name: string, servings: number) => void;
  onDeleteMeal: (id: number) => void;
  onAddIngredient: (
    mealId: number,
    name: string,
    qty: number,
    unit: string,
  ) => void;
  onUpdateIngredient: (
    mealId: number,
    ingredientId: number,
    qty: number,
    unit: string,
  ) => void;
  onRemoveIngredient: (mealId: number, ingredientId: number) => void;
}

export function MealsTab(props: Props) {
  const { state } = props;
  const [selectedMealId, setSelectedMealId] = useState<number | null>(null);

  // Follow the list rather than holding a stale id after a delete.
  const selected =
    state.meals.find((m) => m.id === selectedMealId) ?? state.meals[0] ?? null;

  return (
    <div className="flex flex-col gap-8">
      <AddMealForm onAdd={props.onAddMeal} busy={props.busy} />
      <TemplateGallery
        state={state}
        busy={props.busy}
        onAdd={props.onAddFromTemplate}
      />

      <section>
        <SectionTitle>Your Meals</SectionTitle>
        {state.meals.length === 0 ? (
          <Empty>No meals yet — add your first one above.</Empty>
        ) : (
          <div className="flex flex-col gap-2">
            {state.meals.map((meal) => (
              <MealRow
                key={meal.id}
                meal={meal}
                busy={props.busy}
                onUpdate={props.onUpdateMeal}
                onDelete={props.onDeleteMeal}
              />
            ))}
          </div>
        )}
      </section>

      {selected && (
        <IngredientEditor
          state={state}
          meal={selected}
          busy={props.busy}
          onSelectMeal={setSelectedMealId}
          onAdd={props.onAddIngredient}
          onUpdate={props.onUpdateIngredient}
          onRemove={props.onRemoveIngredient}
        />
      )}
    </div>
  );
}

function AddMealForm({
  onAdd,
  busy,
}: {
  onAdd: (name: string, servings: number) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("");
  // Held as text, not a number. Coercing on every keystroke made the field
  // impossible to clear: it snapped back to 1, so typing "4" gave "14".
  const [servings, setServings] = useState("1");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim(), Math.max(1, Number(servings) || 1));
    setName("");
    setServings("1");
  };

  return (
    <section>
      <SectionTitle>Add a Meal</SectionTitle>
      <Card>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Meal name">
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Spaghetti Bolognese"
            />
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
          <Button type="submit" disabled={busy || !name.trim()}>
            Add Meal
          </Button>
        </form>
      </Card>
    </section>
  );
}

function TemplateGallery({
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

function MealRow({
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

function IngredientEditor({
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

function IngredientRow({
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
