import { ArrowLeft } from "lucide-react";
import { useId, useState } from "react";

import type { IngredientLine, Meal, ParsedIngredient } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { IngredientPreview } from "./IngredientPreview";
import {
  checkRows,
  MAX_LINE_LENGTH,
  plural,
  type Row,
  toLines,
  toRow,
} from "./rows";

/** The server's limit (server/schemas.py), checked here first so a list
 *  that is too long says why rather than failing on sending. */
const MAX_LINES = 100;

export interface PasteActions {
  /** Resolve with the lines as read, or null if reading failed. */
  onRead: (text: string) => Promise<ParsedIngredient[] | null>;
  /** Resolve with the saved meal, or null if saving failed. */
  onSave: (ingredients: IngredientLine[]) => Promise<Meal | null>;
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
  const { valid } = checkRows(rows, kept);

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (!valid) return;
        const saved = await onSave([
          ...kept.map(({ name, qty, unit }) => ({ name, qty, unit })),
          ...toLines(rows),
        ]);
        if (saved) onClose();
      }}
      className="space-y-3 rounded-lg border border-dashed p-3"
    >
      <h4 className="text-sm font-medium">Check what was read</h4>
      <IngredientPreview rows={rows} existing={kept} known={known} onChange={onChange} />

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

