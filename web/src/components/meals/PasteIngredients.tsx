import { ArrowLeft, TriangleAlert, X } from "lucide-react";
import { useId, useState } from "react";

import type { IngredientLine, Meal, ParsedIngredient } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { sameUnit } from "@/lib/quantities";
import { cn } from "@/lib/utils";

/** The server's limits (server/schemas.py), checked here first so a list
 *  that is too long says why rather than failing on sending. */
const MAX_LINES = 100;
const MAX_LINE_LENGTH = 200;

export interface PasteActions {
  /** Resolve with the lines as read, or null if reading failed. */
  onRead: (text: string) => Promise<ParsedIngredient[] | null>;
  /** Resolve with the saved meal, or null if saving failed. */
  onSave: (ingredients: IngredientLine[]) => Promise<Meal | null>;
}

interface Row {
  id: number;
  /** The line as pasted, so the person can see what each row came from. */
  text: string;
  name: string;
  qty: string;
  unit: string;
  /** Doubts the server had: "Read 2 to 3 as 3." */
  notes: string[];
}

/**
 * A whole ingredient list at once: paste it, check what was read, save it
 * in one request. Nothing is saved until the person has seen every row,
 * and any row can be corrected or dropped first.
 */
export function PasteIngredients({
  meal,
  pending,
  known,
  onRead,
  onSave,
  onClose,
}: PasteActions & {
  meal: Meal;
  pending: boolean;
  /** The id of the datalist of ingredient names to suggest. */
  known: string;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);

  if (rows === null) {
    return (
      <PasteBox
        text={text}
        pending={pending}
        onChange={setText}
        onClose={onClose}
        onRead={async () => {
          const lines = await onRead(text);
          if (lines) setRows(lines.map(toRow));
        }}
      />
    );
  }

  return (
    <Preview
      meal={meal}
      rows={rows}
      pending={pending}
      known={known}
      onChange={setRows}
      onBack={() => setRows(null)}
      onClose={onClose}
      onSave={onSave}
    />
  );
}

function toRow(line: ParsedIngredient, id: number): Row {
  return {
    id,
    text: line.text,
    name: line.name,
    qty: line.qty === null ? "" : String(Math.round(line.qty * 1000) / 1000),
    unit: line.unit,
    // "No amount found" is said by the empty, highlighted quantity instead.
    notes: line.warnings.filter((w) => w !== "No amount found."),
  };
}

function PasteBox({
  text,
  pending,
  onChange,
  onRead,
  onClose,
}: {
  text: string;
  pending: boolean;
  onChange: (text: string) => void;
  onRead: () => void;
  onClose: () => void;
}) {
  const id = useId();
  const lines = text.split("\n");
  const count = lines.filter((line) => line.trim()).length;
  const longLine = lines.findIndex((line) => line.trim().length > MAX_LINE_LENGTH);
  const problem =
    count > MAX_LINES
      ? `That's ${count} lines; paste up to ${MAX_LINES} at a time.`
      : longLine >= 0
        ? `Line ${longLine + 1} is longer than ${MAX_LINE_LENGTH} characters.`
        : null;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (count > 0 && !problem) onRead();
      }}
      onKeyDown={(event) => event.key === "Escape" && onClose()}
      className="space-y-3 rounded-lg border border-dashed p-3"
    >
      <div className="space-y-1.5">
        <Label htmlFor={id}>Paste the ingredient list</Label>
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          One per line, as a recipe writes them. You'll check what was read before
          anything is saved.
        </p>
        <Textarea
          id={id}
          value={text}
          autoFocus
          rows={8}
          aria-describedby={`${id}-hint${problem ? ` ${id}-problem` : ""}`}
          aria-invalid={problem ? true : undefined}
          placeholder={"500 g beef mince\n2 onions, diced\n1 x 400 g can chopped tomatoes"}
          onChange={(e) => onChange(e.target.value)}
          className="max-h-96 min-h-40"
        />
        {problem && (
          <p id={`${id}-problem`} className="text-sm text-destructive">
            {problem}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending || count === 0 || problem !== null}>
          Read {count > 1 ? `${count} lines` : "the list"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Preview({
  meal,
  rows,
  pending,
  known,
  onChange,
  onBack,
  onClose,
  onSave,
}: {
  meal: Meal;
  rows: Row[];
  pending: boolean;
  known: string;
  onChange: (rows: Row[]) => void;
  onBack: () => void;
  onClose: () => void;
  onSave: PasteActions["onSave"];
}) {
  const [replace, setReplace] = useState(false);
  const replaceId = useId();
  const kept = replace ? [] : meal.ingredients;
  const clashes = unitClashes(rows, kept);
  const missing = rows.filter((row) => !(Number(row.qty) > 0)).length;
  const valid =
    rows.length > 0 &&
    rows.every((row) => row.name.trim() && Number(row.qty) > 0) &&
    clashes.size === 0;

  const update = (id: number, change: Partial<Row>) =>
    onChange(rows.map((row) => (row.id === id ? { ...row, ...change } : row)));

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (!valid) return;
        const saved = await onSave([
          ...kept.map(({ name, qty, unit }) => ({ name, qty, unit })),
          ...rows.map((row) => ({
            name: row.name.trim(),
            qty: Number(row.qty),
            unit: row.unit.trim(),
          })),
        ]);
        if (saved) onClose();
      }}
      className="space-y-3 rounded-lg border border-dashed p-3"
    >
      <div>
        <h4 className="text-sm font-medium">Check what was read</h4>
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {rows.length === 0
            ? "Every line is removed. Go back to the text to try again."
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
      </div>

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

      {meal.ingredients.length > 0 && (
        <label htmlFor={replaceId} className="flex items-start gap-2 text-sm">
          <input
            id={replaceId}
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
            className="mt-0.5 size-4 accent-primary"
          />
          <span>
            Replace the {plural(meal.ingredients.length, "ingredient")} already on{" "}
            {meal.name}
            <span className="block text-xs text-muted-foreground">
              {replace
                ? "They'll be removed and these saved in their place."
                : "Unticked, these are added to them."}
            </span>
          </span>
        </label>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending || !valid}>
          Save {plural(rows.length, "ingredient")}
        </Button>
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden />
          Back to the text
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
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

/**
 * Rows naming an ingredient that is also listed in a different unit, by row
 * id, with what to tell the person. The server would refuse the whole list
 * (it cannot add 50 g to 1 tbsp), so they are caught here first.
 */
function unitClashes(
  rows: Row[],
  existing: readonly IngredientLine[],
): Map<number, string> {
  const clashes = new Map<number, string>();
  const key = (name: string) => name.trim().toLowerCase();
  for (const row of rows) {
    if (!row.name.trim()) continue;
    const onMeal = existing.find(
      (other) => key(other.name) === key(row.name) && !sameUnit(other.unit, row.unit),
    );
    const listed = rows.find(
      (other) =>
        other.id !== row.id &&
        key(other.name) === key(row.name) &&
        !sameUnit(other.unit, row.unit),
    );
    const other = onMeal ?? listed;
    if (other) {
      const where = onMeal ? "already on this meal" : "also listed";
      clashes.set(
        row.id,
        `${row.name.trim()} is ${where} ${other.unit ? `in ${other.unit}` : "as a count"}. ` +
          "Use the same unit so they add up.",
      );
    }
  }
  return clashes;
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}
