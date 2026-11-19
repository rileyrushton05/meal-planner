import { ArrowLeft, ArrowRight, ExternalLink, Link2 } from "lucide-react";
import { useId, useState } from "react";

import type { AppState, ImportedRecipe, IngredientLine, Meal } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { IngredientPreview, SuggestionLists } from "./IngredientPreview";
import {
  checkRows,
  plural,
  type Row,
  toLines,
  toRow,
} from "./rows";

export interface ImportActions {
  /** Resolve with the recipe as read, or null if it could not be. */
  onImport: (url: string) => Promise<ImportedRecipe | null>;
  /** Resolve with the new meal, or null if creating it failed. */
  onCreate: (name: string, servings: number, ingredients: IngredientLine[]) => Promise<Meal | null>;
}

/**
 * A meal from a recipe website: paste the link, check what was read (name,
 * servings, every ingredient), create it. The server fetches the page;
 * nothing is saved until the person presses Create.
 */
export function ImportRecipe({
  state,
  pending,
  onImport,
  onCreate,
  onPreviewChange,
}: ImportActions & {
  state: AppState;
  pending: boolean;
  /** Told when the preview opens or closes, so the page around it can
   *  step aside while the recipe is checked. */
  onPreviewChange: (open: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  const [recipe, setRecipe] = useState<ImportedRecipe | null>(null);
  const id = useId();

  if (recipe) {
    return (
      <RecipePreview
        recipe={recipe}
        state={state}
        pending={pending}
        onCreate={onCreate}
        onBack={() => {
          setRecipe(null);
          onPreviewChange(false);
        }}
      />
    );
  }

  const link = url.trim();
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (!link) return;
        const found = await onImport(link);
        if (found) {
          setRecipe(found);
          onPreviewChange(true);
        }
      }}
      className="border-t p-4 sm:p-5"
    >
      <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
        Or import from a recipe website
      </h3>
      <p id={`${id}-hint`} className="mt-1 mb-3 text-sm text-muted-foreground">
        Paste the link to a recipe page. Its name, servings and ingredients are read for you
        to check before anything is saved.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1 space-y-1.5">
          <Label htmlFor={id}>Recipe link</Label>
          <div className="relative">
            <Link2
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id={id}
              type="url"
              inputMode="url"
              autoComplete="off"
              aria-describedby={`${id}-hint`}
              placeholder="https://"
              maxLength={2000}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="pl-8"
            />
          </div>
        </div>
        <Button type="submit" variant="outline" disabled={pending || !link}>
          {pending ? "Reading the page…" : "Import"}
        </Button>
      </div>
    </form>
  );
}

function RecipePreview({
  recipe,
  state,
  pending,
  onCreate,
  onBack,
}: {
  recipe: ImportedRecipe;
  state: AppState;
  pending: boolean;
  onCreate: ImportActions["onCreate"];
  onBack: () => void;
}) {
  const [name, setName] = useState(recipe.name);
  const [servings, setServings] = useState(String(recipe.servings ?? 4));
  const [rows, setRows] = useState<Row[]>(() => recipe.lines.map(toRow));
  const id = useId();

  const taken = state.meals.find(
    (meal) => meal.name.toLowerCase() === name.trim().toLowerCase(),
  );
  const { valid } = checkRows(rows, []);
  const count = Number(servings);
  const ready = valid && name.trim() !== "" && !taken && count >= 1;

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (!ready) return;
        // The page opens the new meal; on failure the preview stays, as checked.
        await onCreate(name.trim(), Math.floor(count), toLines(rows));
      }}
      className="space-y-4 border-t p-4 sm:p-5"
    >
      <div>
        <h3 className="font-medium">Check the recipe</h3>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Read from{" "}
          <a
            href={recipe.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-2 hover:text-primary"
          >
            {hostOf(recipe.url)}
            <ExternalLink aria-hidden className="size-3" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          . Nothing is saved until you create the meal.
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-48 flex-1 space-y-1.5">
          <Label htmlFor={`${id}-name`}>Meal name</Label>
          <Input
            id={`${id}-name`}
            value={name}
            maxLength={200}
            aria-invalid={!name.trim() || taken ? true : undefined}
            aria-describedby={`${id}-name-note`}
            onChange={(e) => setName(e.target.value)}
          />
          <p id={`${id}-name-note`} className="text-xs text-destructive">
            {!name.trim()
              ? "The page gave no name; give it one."
              : taken
                ? `You already have a meal called ${taken.name}; name this one differently.`
                : ""}
          </p>
        </div>
        <div className="w-24 space-y-1.5">
          <Label htmlFor={`${id}-servings`}>Servings</Label>
          <Input
            id={`${id}-servings`}
            type="number"
            min={1}
            value={servings}
            aria-describedby={recipe.servings === null ? `${id}-servings-note` : undefined}
            onChange={(e) => setServings(e.target.value)}
          />
        </div>
      </div>
      {recipe.servings === null && (
        <p id={`${id}-servings-note`} className="-mt-2 text-xs text-muted-foreground">
          The page didn't say how many it serves, so check the servings.
        </p>
      )}

      <div>
        <h4 className="mb-1 text-sm font-medium">
          Ingredients <span className="text-muted-foreground tabular-nums">{rows.length}</span>
        </h4>
        <IngredientPreview rows={rows} existing={[]} known="known-ingredients" onChange={setRows} />
      </div>

      {/* The meal panel, which holds these elsewhere, is not on screen. */}
      <SuggestionLists suggestions={state.ingredient_suggestions} />

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending || !ready}>
          Create meal with {plural(rows.length, "ingredient")}
          <ArrowRight aria-hidden />
        </Button>
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden />
          Use a different link
        </Button>
      </div>
    </form>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
