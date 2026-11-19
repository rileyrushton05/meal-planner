import { ArrowLeft, ClipboardList, Pencil, Plus, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";

import type {
  AppState,
  IngredientAmount,
  IngredientLine,
  IngredientSuggestion,
  Meal,
  ParsedIngredient,
} from "@/api/types";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/dates";
import { formatAmount } from "@/lib/quantities";

import { MealAvatar } from "./MealAvatar";
import { SuggestionLists } from "./IngredientPreview";
import { PasteIngredients } from "./PasteIngredients";
import { plannedDays } from "./planned";


export interface MealPanelActions {
  onUpdate: (id: number, name: string, servings: number) => void;
  onDelete: (id: number) => void;
  onAddIngredient: (mealId: number, name: string, qty: number, unit: string) => void;
  onUpdateIngredient: (mealId: number, ingredientId: number, qty: number, unit: string) => void;
  onRemoveIngredient: (mealId: number, ingredientId: number) => void;
  /** Resolve with the lines as read, or null if reading failed. */
  onReadIngredients: (text: string) => Promise<ParsedIngredient[] | null>;
  /** Resolve with the saved meal, or null if saving failed. */
  onReplaceIngredients: (mealId: number, ingredients: IngredientLine[]) => Promise<Meal | null>;
}

/**
 * Everything about one meal in one place: its details, and its ingredients
 * with the field for the next one right under them. An empty meal puts the
 * cursor in that field, so creating a meal flows straight into filling it.
 */
export function MealPanel({
  meal,
  state,
  pending,
  onBack,
  ...actions
}: MealPanelActions & {
  meal: Meal;
  state: AppState;
  pending: boolean;
  onBack: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const days = plannedDays(state.plan, meal.id);
  const titleId = `meal-${meal.id}-title`;

  return (
    <section aria-labelledby={titleId} className="rounded-xl border bg-card">
      <BackToList onBack={onBack} />

      <header className="flex items-start gap-3 border-b p-4 sm:p-5">
        <MealAvatar meal={meal} size="lg" />
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="font-heading text-xl leading-tight font-semibold">
            {meal.name}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Serves {meal.servings}
            {" · "}
            {days.length > 0
              ? `Planned ${days.join(", ")} in the week of ${formatDate(state.week_start)}`
              : `Not planned in the week of ${formatDate(state.week_start)}`}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${meal.name} details`}
            aria-expanded={editing}
            onClick={() => setEditing(!editing)}
          >
            <Pencil aria-hidden />
          </Button>
          <DeleteMeal meal={meal} pending={pending} onDelete={actions.onDelete} />
        </div>
      </header>

      {editing && (
        <MealDetailsForm
          meal={meal}
          pending={pending}
          onSave={(name, servings) => {
            actions.onUpdate(meal.id, name, servings);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}

      <Ingredients meal={meal} state={state} pending={pending} {...actions} />
    </section>
  );
}

/** On a phone the panel replaces the list, so it needs a way back. */
export function BackToList({ onBack }: { onBack?: () => void }) {
  if (!onBack) return null;
  return (
    <div className="border-b px-2 py-1.5 lg:hidden">
      <Button variant="ghost" size="sm" onClick={onBack}>
        <ArrowLeft aria-hidden />
        All meals
      </Button>
    </div>
  );
}

function MealDetailsForm({
  meal,
  pending,
  onSave,
  onCancel,
}: {
  meal: Meal;
  pending: boolean;
  onSave: (name: string, servings: number) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(meal.name);
  // Held as text so the field can be cleared while typing a new number.
  const [servings, setServings] = useState(String(meal.servings));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) onSave(name.trim(), Math.max(1, Number(servings) || 1));
      }}
      onKeyDown={(event) => event.key === "Escape" && onCancel()}
      className="flex flex-wrap items-end gap-3 border-b bg-muted/40 p-4 sm:px-5"
    >
      <div className="min-w-44 flex-1 space-y-1.5">
        <Label htmlFor={`name-${meal.id}`}>Meal name</Label>
        <Input
          id={`name-${meal.id}`}
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="w-24 space-y-1.5">
        <Label htmlFor={`servings-${meal.id}`}>Servings</Label>
        <Input
          id={`servings-${meal.id}`}
          type="number"
          min={1}
          value={servings}
          onChange={(e) => setServings(e.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={pending || !name.trim()}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DeleteMeal({
  meal,
  pending,
  onDelete,
}: {
  meal: Meal;
  pending: boolean;
  onDelete: (id: number) => void;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger
        render={<Button variant="ghost" size="icon" aria-label={`Delete ${meal.name}`} />}
      >
        <Trash2 aria-hidden />
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {meal.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            This also removes its ingredients and takes it off any planned day.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={pending} onClick={() => onDelete(meal.id)}>
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function Ingredients({
  meal,
  state,
  pending,
  onAddIngredient,
  onUpdateIngredient,
  onRemoveIngredient,
  onReadIngredients,
  onReplaceIngredients,
}: MealPanelActions & { meal: Meal; state: AppState; pending: boolean }) {
  const count = meal.ingredients.length;
  const [pasting, setPasting] = useState(false);

  return (
    <div className="p-4 sm:p-5">
      <div className="mb-2 flex min-h-8 items-center justify-between gap-2">
        <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
          Ingredients{count > 0 && <span className="ml-1.5 tabular-nums">{count}</span>}
        </h3>
        {!pasting && (
          <Button variant="ghost" size="sm" onClick={() => setPasting(true)}>
            <ClipboardList aria-hidden />
            Paste a list
          </Button>
        )}
      </div>

      {pasting ? null : count === 0 ? (
        <p className="mb-3 text-sm text-muted-foreground">
          Nothing yet. Add them one at a time below, or paste the list from a recipe. Each
          one goes on the grocery list whenever this meal is planned.
        </p>
      ) : (
        <ul className="mb-3 divide-y">
          {meal.ingredients.map((ingredient) => (
            <IngredientRow
              key={ingredient.ingredient_id}
              mealId={meal.id}
              ingredient={ingredient}
              pending={pending}
              onUpdate={onUpdateIngredient}
              onRemove={onRemoveIngredient}
            />
          ))}
        </ul>
      )}

      {pasting ? (
        <PasteIngredients
          meal={meal}
          pending={pending}
          known="known-ingredients"
          onRead={onReadIngredients}
          onSave={(ingredients) => onReplaceIngredients(meal.id, ingredients)}
          onClose={() => setPasting(false)}
        />
      ) : (
        <AddIngredient
          suggestions={state.ingredient_suggestions}
          pending={pending}
          // An empty meal has one obvious next step, so be ready for it.
          autoFocus={count === 0}
          onAdd={(name, qty, unit) => onAddIngredient(meal.id, name, qty, unit)}
        />
      )}

      <SuggestionLists suggestions={state.ingredient_suggestions} />
    </div>
  );
}

function IngredientRow({
  mealId,
  ingredient,
  pending,
  onUpdate,
  onRemove,
}: {
  mealId: number;
  ingredient: IngredientAmount;
  pending: boolean;
  onUpdate: MealPanelActions["onUpdateIngredient"];
  onRemove: MealPanelActions["onRemoveIngredient"];
}) {
  const [editing, setEditing] = useState(false);
  const [qty, setQty] = useState("");
  const [unit, setUnit] = useState("");
  const valid = Number(qty) > 0;

  // Seeded on opening rather than at mount: the amount can change underneath
  // this row (adding the same ingredient again adds to it), and stale fields
  // would write the old value back on save.
  const startEditing = () => {
    setQty(String(ingredient.qty));
    setUnit(ingredient.unit);
    setEditing(true);
  };

  if (editing) {
    return (
      <li className="py-1.5">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!valid) return;
            onUpdate(mealId, ingredient.ingredient_id, Number(qty), unit.trim());
            setEditing(false);
          }}
          onKeyDown={(event) => event.key === "Escape" && setEditing(false)}
          className="flex flex-wrap items-center gap-2"
        >
          <span className="min-w-24 flex-1 text-sm font-medium">{ingredient.name}</span>
          <Input
            aria-label={`Quantity of ${ingredient.name}`}
            type="number"
            min={0}
            step="any"
            value={qty}
            autoFocus
            onChange={(e) => setQty(e.target.value)}
            className="h-8 w-20"
          />
          <Input
            aria-label={`Unit of ${ingredient.name}`}
            list="common-units"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="h-8 w-20"
          />
          <Button type="submit" size="sm" disabled={pending || !valid}>
            Save
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      </li>
    );
  }

  return (
    <li className="flex items-center gap-1 py-1">
      <button
        type="button"
        onClick={startEditing}
        aria-label={`Edit ${ingredient.name}`}
        className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-md px-1.5 py-1.5 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="truncate font-medium">{ingredient.name}</span>
        <span className="shrink-0 text-muted-foreground tabular-nums">
          {formatAmount(ingredient.qty, ingredient.unit)}
        </span>
      </button>
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={pending}
        aria-label={`Remove ${ingredient.name}`}
        onClick={() => onRemove(mealId, ingredient.ingredient_id)}
      >
        <X aria-hidden />
      </Button>
    </li>
  );
}

/**
 * The next ingredient: name, amount, Enter. Afterwards the cursor goes back
 * to the name, so a whole recipe can be typed without touching the mouse.
 *
 * Picking a known name fills in the unit it is usually measured in (garlic
 * in cloves, mince in g), until the person types a unit of their own.
 */
function AddIngredient({
  suggestions,
  pending,
  autoFocus,
  onAdd,
}: {
  suggestions: readonly IngredientSuggestion[];
  pending: boolean;
  autoFocus: boolean;
  onAdd: (name: string, qty: number, unit: string) => void;
}) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState("");
  const [unit, setUnit] = useState("");
  const [unitTyped, setUnitTyped] = useState(false);
  const nameField = useRef<HTMLInputElement>(null);
  const quantity = Number(qty);
  const valid = name.trim().length > 0 && quantity > 0;
  const usual = (value: string) =>
    suggestions.find((s) => s.name.toLowerCase() === value.trim().toLowerCase());
  const known = usual(name);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onAdd(name.trim(), quantity, unit.trim());
        setName("");
        setQty("");
        setUnit("");
        setUnitTyped(false);
        nameField.current?.focus();
      }}
      className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-end gap-2 rounded-lg border border-dashed p-3 sm:grid-cols-[minmax(0,1fr)_5.5rem_5.5rem_auto]"
    >
      <div className="col-span-3 space-y-1.5 sm:col-span-1">
        <Label htmlFor="ingredient-name" className="text-xs text-muted-foreground">
          Ingredient
        </Label>
        {/* A datalist suggests known ingredients while still accepting a
            new one, which a closed dropdown would not. */}
        <Input
          ref={nameField}
          id="ingredient-name"
          list="known-ingredients"
          value={name}
          autoFocus={autoFocus}
          onChange={(e) => {
            setName(e.target.value);
            if (!unitTyped) setUnit(usual(e.target.value)?.unit ?? "");
          }}
          placeholder="e.g. Pasta"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="ingredient-qty" className="text-xs text-muted-foreground">
          Quantity
        </Label>
        <Input
          id="ingredient-qty"
          type="number"
          min={0}
          step="any"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="ingredient-unit" className="text-xs text-muted-foreground">
          Unit
        </Label>
        <Input
          id="ingredient-unit"
          list="common-units"
          value={unit}
          onChange={(e) => {
            setUnit(e.target.value);
            setUnitTyped(true);
          }}
          // A known item counted rather than measured: say so, or the empty
          // field looks like something was missed.
          placeholder={known && !known.unit && !unitTyped ? "none" : "g, ml"}
        />
      </div>
      <Button type="submit" disabled={pending || !valid} aria-label="Add ingredient">
        <Plus aria-hidden />
        <span className="hidden sm:inline">Add</span>
      </Button>
    </form>
  );
}
