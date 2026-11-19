import { describe, expect, it } from "vitest";

import { makeMeal } from "@/test/factories";

import { formatAmount, formatQty, sameUnit, scaledIngredients } from "./quantities";

describe("formatQty", () => {
  it.each([
    [400, "400"],
    [1.5, "1.5"],
    [1 / 3, "0.33"],
    [0.1 + 0.2, "0.3"],
    [2.0, "2"],
  ])("writes %s as %s", (qty, text) => {
    expect(formatQty(qty)).toBe(text);
  });

  it("leaves no stray space after a count", () => {
    expect(formatAmount(2, "")).toBe("2");
    expect(formatAmount(250, "g")).toBe("250 g");
  });

  it.each([
    [1, "cloves", "1 clove"],
    [2, "cloves", "2 cloves"],
    [1, "pinches", "1 pinch"],
    [0.5, "cups", "0.5 cups"],
    [1.001, "cans", "1 can"],
    [1, "kg", "1 kg"],
  ])("writes %s %s as %s", (qty, unit, text) => {
    expect(formatAmount(qty, unit)).toBe(text);
  });
});

describe("sameUnit", () => {
  it("ignores case, spacing and plural", () => {
    expect(sameUnit("clove", "Cloves")).toBe(true);
    expect(sameUnit(" g", "g")).toBe(true);
    expect(sameUnit("", "")).toBe(true);
  });

  it("keeps different units apart, even of one kind", () => {
    expect(sameUnit("g", "kg")).toBe(false);
    expect(sameUnit("", "g")).toBe(false);
  });
});

describe("scaledIngredients", () => {
  const meal = makeMeal({
    servings: 4,
    ingredients: [{ ingredient_id: 1, name: "Rice", qty: 300, unit: "g" }],
  });

  it("scales a recipe to the number cooked for", () => {
    expect(scaledIngredients(meal, 2)[0].qty).toBe(150);
    expect(scaledIngredients(meal, 6)[0].qty).toBe(450);
  });

  it("leaves a recipe with no servings as written, rather than dividing by zero", () => {
    expect(scaledIngredients({ ...meal, servings: 0 }, 3)[0].qty).toBe(300);
  });
});
