import type { Category, GroceryLine } from "@/api/types";

/** The aisles in the order a supermarket is walked (the server's `Category`
 *  order), with the names a shopper reads. */
const AISLES: readonly { category: Category; label: string }[] = [
  { category: "produce", label: "Fruit & veg" },
  { category: "meat", label: "Meat & seafood" },
  { category: "dairy", label: "Dairy & eggs" },
  { category: "bakery", label: "Bakery" },
  { category: "pantry", label: "Pantry" },
  { category: "frozen", label: "Frozen" },
];

export interface Aisle<T> {
  /** Null for the things the catalogue does not know, which come last. */
  category: Category | null;
  label: string;
  lines: T[];
}

const order = (category: Category | null) => {
  const index = AISLES.findIndex((aisle) => aisle.category === category);
  return index === -1 ? AISLES.length : index;
};

/**
 * Lines grouped by aisle, in shopping order, each aisle keeping the order
 * the lines came in. Aisles with nothing in them are left out.
 */
export function byAisle<T extends Pick<GroceryLine, "category">>(lines: readonly T[]): Aisle<T>[] {
  const groups = new Map<Category | null, T[]>();
  for (const line of lines) {
    const category = line.category ?? null;
    groups.set(category, [...(groups.get(category) ?? []), line]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => order(a) - order(b))
    .map(([category, of]) => ({
      category,
      label: AISLES.find((aisle) => aisle.category === category)?.label ?? "Other",
      lines: of,
    }));
}

/**
 * The list as text to send to someone: under aisle headings when it spans
 * more than one aisle, plain when a heading would say nothing.
 */
export function listAsText(lines: readonly GroceryLine[]): string {
  const item = (line: GroceryLine) => `- ${line.name}: ${line.display}`;
  const aisles = byAisle(lines);
  if (aisles.length < 2) return lines.map(item).join("\n");
  return aisles.map((aisle) => [aisle.label, ...aisle.lines.map(item)].join("\n")).join("\n\n");
}
