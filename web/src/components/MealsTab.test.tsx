import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeMeal, makeState, makeTemplate } from "../test/factories";
import { MealsTab } from "./MealsTab";

function renderTab(overrides = {}) {
  const props = {
    state: makeState(),
    busy: false,
    onAddMeal: vi.fn(),
    onAddFromTemplate: vi.fn(),
    onUpdateMeal: vi.fn(),
    onDeleteMeal: vi.fn(),
    onAddIngredient: vi.fn(),
    onUpdateIngredient: vi.fn(),
    onRemoveIngredient: vi.fn(),
    ...overrides,
  };
  return { ...render(<MealsTab {...props} />), props };
}

describe("adding a meal", () => {
  it("submits the trimmed name and servings", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.type(screen.getByLabelText("Meal name"), "  Spaghetti  ");
    await user.clear(screen.getByLabelText("Servings"));
    await user.type(screen.getByLabelText("Servings"), "4");
    await user.click(screen.getByRole("button", { name: "Add Meal" }));

    expect(props.onAddMeal).toHaveBeenCalledWith("Spaghetti", 4);
  });

  it("will not submit a blank name", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.type(screen.getByLabelText("Meal name"), "   ");
    await user.click(screen.getByRole("button", { name: "Add Meal" }));

    expect(props.onAddMeal).not.toHaveBeenCalled();
  });

  it("clears the form after a submission", async () => {
    const user = userEvent.setup();
    renderTab();

    const name = screen.getByLabelText("Meal name");
    await user.type(name, "Tacos");
    await user.click(screen.getByRole("button", { name: "Add Meal" }));

    expect(name).toHaveValue("");
  });
});

describe("deleting a meal", () => {
  const state = makeState({ meals: [makeMeal({ name: "Spaghetti" })] });

  it("asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(props.onDeleteMeal).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("deletes once confirmed", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Yes, delete" }));

    expect(props.onDeleteMeal).toHaveBeenCalledWith(1);
  });

  it("does nothing when cancelled", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(props.onDeleteMeal).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});

describe("adding an ingredient", () => {
  const state = makeState({
    meals: [makeMeal({ id: 1, name: "Spaghetti" })],
    ingredient_names: ["Pasta"],
  });

  it("requires a quantity greater than zero", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.type(screen.getByLabelText("Ingredient"), "Pasta");
    await user.type(screen.getByLabelText("Quantity"), "0");

    expect(screen.getByRole("button", { name: "Add Ingredient" })).toBeDisabled();
    expect(props.onAddIngredient).not.toHaveBeenCalled();
  });

  it("submits name, quantity and unit", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.type(screen.getByLabelText("Ingredient"), "Pasta");
    await user.type(screen.getByLabelText("Quantity"), "200");
    await user.type(screen.getByLabelText("Unit"), "g");
    await user.click(screen.getByRole("button", { name: "Add Ingredient" }));

    expect(props.onAddIngredient).toHaveBeenCalledWith(1, "Pasta", 200, "g");
  });

  it("accepts an ingredient that is not in the known list", async () => {
    // Regression test: an earlier autocomplete-only field made it
    // impossible to add anything without an existing match.
    const user = userEvent.setup();
    const { props } = renderTab({ state });

    await user.type(screen.getByLabelText("Ingredient"), "Bread");
    await user.type(screen.getByLabelText("Quantity"), "4");
    await user.type(screen.getByLabelText("Unit"), "slices");
    await user.click(screen.getByRole("button", { name: "Add Ingredient" }));

    expect(props.onAddIngredient).toHaveBeenCalledWith(1, "Bread", 4, "slices");
  });

  it("offers known ingredients as suggestions", () => {
    renderTab({ state });

    const input = screen.getByLabelText("Ingredient");
    const list = document.getElementById(input.getAttribute("list") ?? "");
    const options = Array.from(list?.querySelectorAll("option") ?? []);
    expect(options.map((o) => o.value)).toEqual(["Pasta"]);
  });
});

describe("templates", () => {
  const template = makeTemplate({ name: "Omelette" });

  it("adds a template on click", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ state: makeState({ templates: [template] }) });

    await user.click(
      screen.getByRole("button", { name: /quick add from templates/i }),
    );
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(props.onAddFromTemplate).toHaveBeenCalledWith("Omelette");
  });

  it("disables a template that has already been added", async () => {
    const user = userEvent.setup();
    renderTab({
      state: makeState({
        templates: [template],
        meals: [makeMeal({ name: "omelette" })],
      }),
    });

    await user.click(
      screen.getByRole("button", { name: /quick add from templates/i }),
    );

    // Matched case-insensitively, the same way the API rejects duplicates.
    expect(screen.getByRole("button", { name: "Added" })).toBeDisabled();
  });
});

describe("empty state", () => {
  it("prompts for a first meal", () => {
    renderTab();
    expect(screen.getByText(/no meals yet/i)).toBeInTheDocument();
  });
});
