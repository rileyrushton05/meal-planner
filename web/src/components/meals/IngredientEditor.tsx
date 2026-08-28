import { Plus, X } from "lucide-react";
import { useState } from "react";

import type { AppState, IngredientAmount, Meal } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Ingredients</h2>
        <div className="w-56">
          <Select
            value={String(meal.id)}
            onValueChange={(value) => onSelectMeal(Number(value))}
          >
            <SelectTrigger aria-label="Select meal" className="w-full">
              {/* Base UI hands the raw value to the trigger, so without this
                  render function the meal's id shows instead of its name. */}
              <SelectValue>
                {(value: string) =>
                  state.meals.find((m) => String(m.id) === value)?.name ?? ""
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {state.meals.map((m) => (
                <SelectItem key={m.id} value={String(m.id)}>
                  {m.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4"
      >
        <div className="min-w-40 flex-1 space-y-2">
          <Label htmlFor="ingredient-name">Ingredient</Label>
          {/* A datalist gives suggestions while still accepting anything
              typed, which a closed dropdown would not. */}
          <Input
            id="ingredient-name"
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
        </div>
        <div className="w-24 space-y-2">
          <Label htmlFor="ingredient-qty">Quantity</Label>
          <Input
            id="ingredient-qty"
            type="number"
            min={0}
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="200"
          />
        </div>
        <div className="w-28 space-y-2">
          <Label htmlFor="ingredient-unit">Unit</Label>
          <Input
            id="ingredient-unit"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="g, ml"
          />
        </div>
        <Button type="submit" disabled={busy || !valid}>
          <Plus className="size-4" />
          Add ingredient
        </Button>
      </form>

      {meal.ingredients.length === 0 ? (
        <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
          No ingredients on {meal.name} yet.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {meal.ingredients.map((ingredient) => (
            <IngredientChip
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
    </section>
  );
}

function IngredientChip({
  mealId,
  ingredient,
  busy,
  onUpdate,
  onRemove,
}: {
  mealId: number;
  ingredient: IngredientAmount;
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

  if (editing) {
    return (
      <div className="flex items-end gap-2 rounded-lg border bg-card p-2">
        <div className="w-20 space-y-1">
          <Label
            htmlFor={`qty-${ingredient.ingredient_id}`}
            className="text-xs text-muted-foreground"
          >
            Quantity
          </Label>
          <Input
            id={`qty-${ingredient.ingredient_id}`}
            type="number"
            min={0}
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="h-8"
          />
        </div>
        <div className="w-20 space-y-1">
          <Label
            htmlFor={`unit-${ingredient.ingredient_id}`}
            className="text-xs text-muted-foreground"
          >
            Unit
          </Label>
          <Input
            id={`unit-${ingredient.ingredient_id}`}
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="h-8"
          />
        </div>
        <Button
          size="sm"
          disabled={busy || !(Number(qty) > 0)}
          onClick={() => {
            onUpdate(mealId, ingredient.ingredient_id, Number(qty), unit.trim());
            setEditing(false);
          }}
        >
          Save
        </Button>
      </div>
    );
  }

  return (
    <span className="flex items-center gap-2 rounded-lg border bg-card py-1.5 pr-1.5 pl-3 text-sm">
      <button
        onClick={() => setEditing(true)}
        aria-label={`Edit ${ingredient.name}`}
        className="hover:text-primary"
      >
        {ingredient.name}
        <span className="ml-2 font-mono text-xs text-muted-foreground">
          {ingredient.qty} {ingredient.unit}
        </span>
      </button>
      <Button
        variant="ghost"
        size="icon"
        className="size-6"
        disabled={busy}
        aria-label={`Remove ${ingredient.name}`}
        onClick={() => onRemove(mealId, ingredient.ingredient_id)}
      >
        <X className="size-3.5" />
      </Button>
    </span>
  );
}
