import type { IngredientLine, ParsedIngredient } from "@/api/types";
import { sameUnit } from "@/lib/quantities";

/** The longest line the server reads (server/schemas.py). */
export const MAX_LINE_LENGTH = 200;

/** One line of a preview, as the person is editing it. */
export interface Row {
  id: number;
  /** The line as pasted, so the person can see what each row came from. */
  text: string;
  name: string;
  qty: string;
  unit: string;
  /** Doubts the server had: "Read 2 to 3 as 3." */
  notes: string[];
}

export function toRow(line: ParsedIngredient, id: number): Row {
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

/** The rows as the API saves them. */
export function toLines(rows: readonly Row[]): IngredientLine[] {
  return rows.map((row) => ({
    name: row.name.trim(),
    qty: Number(row.qty),
    unit: row.unit.trim(),
  }));
}

/**
 * Whether the rows can be saved alongside `existing`, and what is wrong
 * with any that cannot: every row needs a name and an amount, and no
 * ingredient may be listed in two units.
 */
export function checkRows(rows: readonly Row[], existing: readonly IngredientLine[]) {
  const clashes = unitClashes(rows, existing);
  const missing = rows.filter((row) => !(Number(row.qty) > 0)).length;
  const valid =
    rows.length > 0 &&
    rows.every((row) => row.name.trim() && Number(row.qty) > 0) &&
    clashes.size === 0;
  return { clashes, missing, valid };
}

/**
 * Rows naming an ingredient that is also listed in a different unit, by row
 * id, with what to tell the person. The server would refuse the whole list
 * (it cannot add 50 g to 1 tbsp), so they are caught here first.
 */
function unitClashes(
  rows: readonly Row[],
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

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}
