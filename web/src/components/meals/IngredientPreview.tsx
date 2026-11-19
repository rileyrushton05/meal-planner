import { TriangleAlert, X } from "lucide-react";
import { useId } from "react";

import type { IngredientLine, IngredientSuggestion } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { checkRows, MAX_LINE_LENGTH, plural, type Row } from "./rows";

/** Units offered as suggestions, spelled as the server stores them. */
const COMMON_UNITS = ["g", "kg", "ml", "L", "tsp", "tbsp", "cups", "cloves", "slices", "cans"];

/**
 * The lists the ingredient fields suggest from: names (`known-ingredients`)
 * and units (`common-units`). Rendered once wherever such fields are, and
 * outside any form grid: as a grid child, even a hidden datalist picks up
 * the column's spacing and knocks the inputs out of line.
 */
export function SuggestionLists({
  suggestions,
}: {
  suggestions: readonly IngredientSuggestion[];
}) {
  return (
    <>
      <datalist id="known-ingredients">
        {suggestions.map((s) => (
          <option key={s.name} value={s.name} />
        ))}
      </datalist>
      <datalist id="common-units">
        {COMMON_UNITS.map((u) => (
          <option key={u} value={u} />
        ))}
      </datalist>
    </>
  );
}

/**
 * Lines read from a paste or a recipe page, each editable and removable,
 * with what was doubtful about it said under it. Nothing here saves: the
 * form around it does, once `checkRows` says it can.
 */
export function IngredientPreview({
  rows,
  existing,
  known,
  onChange,
}: {
  rows: Row[];
  /** Ingredients the rows will be saved alongside, for the unit check. */
  existing: readonly IngredientLine[];
  /** The id of the datalist of ingredient names to suggest. */
  known: string;
  onChange: (rows: Row[]) => void;
}) {
  const { clashes, missing } = checkRows(rows, existing);
  const update = (id: number, change: Partial<Row>) =>
    onChange(rows.map((row) => (row.id === id ? { ...row, ...change } : row)));

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {rows.length === 0
          ? "Every line is removed."
          : missing > 0
            ? `${plural(missing, "line")} without an amount. Enter one, or remove ${missing === 1 ? "it" : "them"}. `
            : "Correct anything that's wrong, then save."}
        {rows.length > 0 && missing > 0 && (
          // "Salt to taste", "oil for frying": often several, rarely bought
          // for one recipe, so dropping them all is one click.
          <button
            type="button"
            className="font-medium text-foreground underline underline-offset-2 hover:text-primary"
            onClick={() => onChange(rows.filter((row) => Number(row.qty) > 0))}
          >
            Remove {missing === 1 ? "it" : `all ${missing}`}
          </button>
        )}
      </p>

      {rows.length > 0 && (
        <div>
          <div
            aria-hidden
            className="hidden grid-cols-[minmax(0,1fr)_5rem_5.5rem_2rem] gap-2 px-0.5 pb-1 text-xs text-muted-foreground sm:grid"
          >
            <span>Ingredient</span>
            <span>Quantity</span>
            <span>Unit</span>
          </div>
          <ol className="divide-y">
            {rows.map((row, index) => (
              <PreviewRow
                key={row.id}
                row={row}
                line={index + 1}
                clash={clashes.get(row.id)}
                known={known}
                onChange={(change) => update(row.id, change)}
                onRemove={() => onChange(rows.filter((r) => r.id !== row.id))}
              />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function PreviewRow({
  row,
  line,
  clash,
  known,
  onChange,
  onRemove,
}: {
  row: Row;
  line: number;
  clash: string | undefined;
  known: string;
  onChange: (change: Partial<Row>) => void;
  onRemove: () => void;
}) {
  const noteId = useId();
  const noAmount = !(Number(row.qty) > 0);
  const noName = !row.name.trim();
  const problems = [
    noName && "Give it a name.",
    noAmount && "No amount found. Enter one, or remove this line.",
    clash,
  ].filter((p): p is string => Boolean(p));
  const notes = [...problems, ...row.notes];

  return (
    <li className="py-2">
      <p className="mb-1 truncate text-xs text-muted-foreground" title={row.text}>
        <span className="sr-only">Line {line}: </span>
        {row.text}
      </p>
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-2 sm:grid-cols-[minmax(0,1fr)_5rem_5.5rem_2rem]">
        <Input
          aria-label={`Ingredient on line ${line}`}
          aria-describedby={notes.length ? noteId : undefined}
          aria-invalid={noName || clash ? true : undefined}
          list={known}
          value={row.name}
          maxLength={MAX_LINE_LENGTH}
          onChange={(e) => onChange({ name: e.target.value })}
          className="col-span-3 h-8 sm:col-span-1"
        />
        <Input
          aria-label={`Quantity on line ${line}`}
          aria-describedby={notes.length ? noteId : undefined}
          aria-invalid={noAmount ? true : undefined}
          type="number"
          min={0}
          step="any"
          value={row.qty}
          onChange={(e) => onChange({ qty: e.target.value })}
          className="h-8"
        />
        <Input
          aria-label={`Unit on line ${line}`}
          aria-describedby={notes.length ? noteId : undefined}
          aria-invalid={clash ? true : undefined}
          list="common-units"
          value={row.unit}
          maxLength={50}
          placeholder="none"
          onChange={(e) => onChange({ unit: e.target.value })}
          className="h-8"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove line ${line}`}
          onClick={onRemove}
        >
          <X aria-hidden />
        </Button>
      </div>
      {notes.length > 0 && (
        <ul id={noteId} className="mt-1 space-y-0.5 text-xs">
          {notes.map((note) => (
            <li
              key={note}
              className={cn(
                "flex items-start gap-1",
                problems.includes(note) ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {problems.includes(note) && (
                <TriangleAlert aria-hidden className="mt-px size-3 shrink-0" />
              )}
              {note}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
