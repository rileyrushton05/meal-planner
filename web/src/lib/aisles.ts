import type { Category, GroceryLine } from "@/api/types";

/** The names a shopper reads, in the default order (the server's
 *  `Category` order: the way most supermarkets are walked). */
const LABELS: Record<Category, string> = {
  produce: "Fruit & veg",
  meat: "Meat & seafood",
  dairy: "Dairy & eggs",
  bakery: "Bakery",
  pantry: "Pantry",
  frozen: "Frozen",
};

export const DEFAULT_AISLE_ORDER = Object.keys(LABELS) as Category[];

export const aisleLabel = (category: Category | null) =>
  category ? LABELS[category] : "Other";

export interface Aisle<T> {
  /** Null for the things the catalogue does not know, which come last. */
  category: Category | null;
  label: string;
  lines: T[];
}

/**
 * Lines grouped by aisle, in `order` (the person's shop), each aisle
 * keeping the order the lines came in. Aisles with nothing in them are
 * left out.
 */
export function byAisle<T extends Pick<GroceryLine, "category">>(
  lines: readonly T[],
  order: readonly Category[] = DEFAULT_AISLE_ORDER,
): Aisle<T>[] {
  const position = (category: Category | null) => {
    const index = category === null ? -1 : order.indexOf(category);
    return index === -1 ? order.length : index;
  };
  const groups = new Map<Category | null, T[]>();
  for (const line of lines) {
    const category = line.category ?? null;
    groups.set(category, [...(groups.get(category) ?? []), line]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => position(a) - position(b))
    .map(([category, of]) => ({ category, label: aisleLabel(category), lines: of }));
}

/**
 * The list as text to send to someone: under aisle headings when it spans
 * more than one aisle, plain when a heading would say nothing.
 */
export function listAsText(
  lines: readonly GroceryLine[],
  order: readonly Category[] = DEFAULT_AISLE_ORDER,
): string {
  const item = (line: GroceryLine) =>
    line.display ? `- ${line.name}: ${line.display}` : `- ${line.name}`;
  const aisles = byAisle(lines, order);
  if (aisles.length < 2) return lines.map(item).join("\n");
  return aisles.map((aisle) => [aisle.label, ...aisle.lines.map(item)].join("\n")).join("\n\n");
}
