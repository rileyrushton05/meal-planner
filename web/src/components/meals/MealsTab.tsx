import { useState } from "react";

import type { AppState } from "@/api/types";
import { AddMealForm } from "./AddMealForm";
import { IngredientEditor } from "./IngredientEditor";
import { MealRow } from "./MealRow";
import { TemplateGallery } from "./TemplateGallery";

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
    <div className="space-y-8">
      <div className="space-y-3">
        <AddMealForm onAdd={props.onAddMeal} busy={props.busy} />
        <TemplateGallery
          state={state}
          busy={props.busy}
          onAdd={props.onAddFromTemplate}
        />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Your meals</h2>
        {state.meals.length === 0 ? (
          <p className="rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
            No meals yet — add one above, or start from a template.
          </p>
        ) : (
          <div className="grid gap-2 lg:grid-cols-2">
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
