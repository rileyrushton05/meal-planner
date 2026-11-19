import { Plus } from "lucide-react";

import type { AppState, Meal } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useSearchParam } from "@/lib/location";
import { cn } from "@/lib/utils";

import { MealList } from "./MealList";
import { MealPanel, type MealPanelActions } from "./MealPanel";
import { NewMealPanel } from "./NewMealPanel";

interface Props extends Omit<MealPanelActions, "onUpdate" | "onDelete"> {
  state: AppState;
  pending: boolean;
  /** Resolve with the new meal (or null if it failed), so it can be opened. */
  onAddMeal: (name: string, servings: number) => Promise<Meal | null>;
  onAddFromTemplate: (name: string) => Promise<Meal | null>;
  onUpdateMeal: MealPanelActions["onUpdate"];
  onDeleteMeal: MealPanelActions["onDelete"];
}

/** `?meal=` holds a meal's id, "new", or nothing. */
const parseSelection = (raw: string | null) => raw ?? "";

/**
 * A list of meals beside the open one. On a phone the two take turns: the
 * list, then the meal full width with a way back.
 *
 * The open meal lives in the URL, so a refresh or a shared link reopens it.
 */
export function MealsTab({ state, pending, ...props }: Props) {
  const [selection, setSelection] = useSearchParam("meal", parseSelection);

  const selected = /^\d+$/.test(selection)
    ? (state.meals.find((m) => m.id === Number(selection)) ?? null)
    : null;
  // With no meals yet, the only thing to do is make one.
  const view =
    selection === "new" || state.meals.length === 0 ? "new" : selected ? "meal" : "none";
  const backToList = () => setSelection("");

  const open = (meal: Meal | null) => {
    if (meal) setSelection(String(meal.id));
  };

  return (
    // The open meal stops at a reading width: on a wide screen an ingredient's
    // amount would otherwise sit a long way from its name.
    <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,52rem)] lg:items-start">
      <MealList
        meals={state.meals}
        plan={state.plan}
        selectedId={selected?.id ?? null}
        onSelect={(id) => setSelection(String(id))}
        onNew={() => setSelection("new")}
        className={cn(view !== "none" && "hidden lg:block")}
      />

      {/* Sticky, so a long list can scroll while the open meal stays put. */}
      <div className={cn("lg:sticky lg:top-6", view === "none" && "hidden lg:block")}>
        {view === "new" ? (
          <NewMealPanel
            state={state}
            pending={pending}
            onBack={state.meals.length > 0 ? backToList : undefined}
            onCreate={async (name, servings) => open(await props.onAddMeal(name, servings))}
            onCreateFromTemplate={async (name) => open(await props.onAddFromTemplate(name))}
          />
        ) : view === "meal" && selected ? (
          <MealPanel
            // A fresh panel per meal, so an open edit never carries across.
            key={selected.id}
            meal={selected}
            state={state}
            pending={pending}
            onBack={backToList}
            onUpdate={props.onUpdateMeal}
            onDelete={props.onDeleteMeal}
            onAddIngredient={props.onAddIngredient}
            onUpdateIngredient={props.onUpdateIngredient}
            onRemoveIngredient={props.onRemoveIngredient}
            onReadIngredients={props.onReadIngredients}
            onReplaceIngredients={props.onReplaceIngredients}
          />
        ) : (
          <div className="rounded-xl border border-dashed p-10 text-center">
            <p className="font-heading text-lg font-semibold">Pick a meal to see its ingredients</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Or start a new one: name it, then add what goes in it.
            </p>
            <Button className="mt-4" onClick={() => setSelection("new")}>
              <Plus aria-hidden />
              Start a new meal
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
