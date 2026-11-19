import type { IngredientAmount, Meal } from "@/api/types";

/**
 * A quantity without float noise or a trailing ".0": 400, 1.5, 0.33. Two
 * places, like the server's `units.format_qty`, so the grocery list and a
 * meal's ingredients agree.
 */
export function formatQty(qty: number): string {
  return String(Math.round(qty * 100) / 100);
}

/**
 * Counted units are stored plural, so every amount of a thing adds up
 * ("1 cloves" and "2 cloves" are one grocery line); exactly one reads
 * singular. The same list as the server's `units._SINGULAR`.
 */
const SINGULAR: Readonly<Record<string, string>> = {
  cups: "cup",
  cloves: "clove",
  slices: "slice",
  rashers: "rasher",
  stalks: "stalk",
  sticks: "stick",
  sprigs: "sprig",
  pinches: "pinch",
  dashes: "dash",
  handfuls: "handful",
  bunches: "bunch",
  cans: "can",
  jars: "jar",
  packets: "packet",
  bottles: "bottle",
  punnets: "punnet",
  bags: "bag",
  tubs: "tub",
  cartons: "carton",
};

/** "400 g", "2 cloves", "1 clove", or "3" for a count. */
export function formatAmount(qty: number, unit: string): string {
  const shown = formatQty(qty);
  const word = shown === "1" ? (SINGULAR[unit] ?? unit) : unit;
  return `${shown} ${word}`.trim();
}

/**
 * Whether two units are the same once spelling is ignored: "clove" and
 * "Cloves" are, "g" and "kg" are not (the server keeps those apart, as it
 * refuses to add 50 g to 1 kg of the same thing on one meal).
 */
export function sameUnit(a: string, b: string): boolean {
  const key = (unit: string) => {
    const lower = unit.trim().toLowerCase();
    return SINGULAR[lower] ?? lower;
  };
  return key(a) === key(b);
}

/**
 * A meal's ingredients for a different number of people: a recipe for 4
 * cooked for 2 needs half of everything. The grocery list scales the same
 * way, server side.
 */
export function scaledIngredients(meal: Meal, servings: number): IngredientAmount[] {
  const scale = meal.servings > 0 ? servings / meal.servings : 1;
  return meal.ingredients.map((ingredient) => ({
    ...ingredient,
    qty: ingredient.qty * scale,
  }));
}
