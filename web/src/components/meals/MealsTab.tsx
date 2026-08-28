import { useState } from "react";

import type { AppState } from "../../api/types";
import { Empty, SectionTitle } from "../ui";
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
