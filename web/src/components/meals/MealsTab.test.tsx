import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AppState, IngredientLine, Meal, ParsedIngredient } from "@/api/types";
import { MealsTab } from "@/components/meals/MealsTab";
import { makeMeal, makeState, makeTemplate } from "@/test/factories";

function renderTab(state: AppState = makeState(), path = "/meals") {
  window.history.replaceState(null, "", path);
  const props = {
    state,
    pending: false,
    onAddMeal: vi.fn(async (): Promise<Meal | null> => null),
    onAddFromTemplate: vi.fn(async (): Promise<Meal | null> => null),
    onUpdateMeal: vi.fn(),
    onDeleteMeal: vi.fn(),
    onAddIngredient: vi.fn(),
    onUpdateIngredient: vi.fn(),
    onRemoveIngredient: vi.fn(),
    onReadIngredients: vi.fn(async (): Promise<ParsedIngredient[] | null> => null),
    onReplaceIngredients: vi.fn(
      async (_id: number, _lines: IngredientLine[]): Promise<Meal | null> => null,
    ),
  };
  return { ...render(<MealsTab {...props} />), props };
}

function parsed(overrides: Partial<ParsedIngredient>): ParsedIngredient {
  return {
    text: "",
    qty: 1,
    unit: "",
    name: "",
    prep: "",
    catalog_item: null,
    confidence: "high",
    warnings: [],
    ...overrides,
  };
}

const selection = () => new URLSearchParams(window.location.search).get("meal");

const spaghetti = makeMeal({
  id: 1,
  name: "Spaghetti",
  servings: 4,
  ingredients: [{ ingredient_id: 7, name: "Pasta", qty: 400, unit: "g" }],
});
const tacos = makeMeal({ id: 2, name: "Tacos", servings: 2 });

beforeEach(() => {
  window.history.replaceState(null, "", "/meals");
});

describe("finding and opening a meal", () => {
  const state = makeState({
    meals: [spaghetti, tacos],
    plan: [
      { day: "Monday", meal_id: 1, servings: 4 },
      { day: "Saturday", meal_id: 1, servings: 2 },
    ],
  });

  it("lists each meal with what it serves, what's in it and when it's planned", () => {
    renderTab(state);

    const row = screen.getByRole("article", { name: "Spaghetti" });
    expect(row).toHaveTextContent("Serves 4 · 1 ingredient");
    expect(row).toHaveTextContent("Mon · Sat");
    expect(screen.getByRole("article", { name: "Tacos" })).toHaveTextContent(
      "Serves 2 · 0 ingredients",
    );
  });

  it("opens a meal beside the list, and puts it in the URL", async () => {
    const user = userEvent.setup();
    renderTab(state);

    await user.click(within(screen.getByRole("article", { name: "Tacos" })).getByRole("button"));

    expect(screen.getByRole("heading", { level: 2, name: "Tacos" })).toBeInTheDocument();
    expect(selection()).toBe("2");
    expect(
      within(screen.getByRole("article", { name: "Tacos" })).getByRole("button"),
    ).toHaveAttribute("aria-current", "true");
  });

  it("opens the meal named in a link", () => {
    renderTab(state, "/meals?meal=1");
    expect(screen.getByRole("heading", { level: 2, name: "Spaghetti" })).toBeInTheDocument();
    expect(screen.getByText(/Planned Mon, Sat in the week of/)).toBeInTheDocument();
  });

  it("offers a choice when the link's meal no longer exists", () => {
    renderTab(state, "/meals?meal=99");
    expect(screen.getByText("Pick a meal to see its ingredients")).toBeInTheDocument();
  });

  it("narrows the list as you search, and says when nothing matches", async () => {
    const user = userEvent.setup();
    renderTab(state);

    await user.type(screen.getByLabelText("Search meals"), "tac");
    expect(screen.queryByRole("article", { name: "Spaghetti" })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Tacos" })).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Search meals"));
    await user.type(screen.getByLabelText("Search meals"), "curry");
    expect(screen.getByText("No meals match “curry”.")).toBeInTheDocument();
  });

  it("goes back to the list from an open meal (on a phone, they take turns)", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "All meals" }));

    expect(selection()).toBeNull();
    expect(screen.getByText("Pick a meal to see its ingredients")).toBeInTheDocument();
  });
});

describe("creating a meal", () => {
  it("starts on the new meal form when there are no meals yet", () => {
    renderTab();
    expect(screen.getByRole("heading", { name: "New meal" })).toBeInTheDocument();
    expect(screen.getByLabelText("Meal name")).toHaveFocus();
    expect(screen.getByText(/no meals yet/i)).toBeInTheDocument();
  });

  it("submits the trimmed name and servings, and never a blank name", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(makeState({ meals: [tacos] }), "/meals?meal=new");

    await user.type(screen.getByLabelText("Meal name"), "   ");
    expect(screen.getByRole("button", { name: /create meal/i })).toBeDisabled();

    await user.type(screen.getByLabelText("Meal name"), "  Spaghetti  ");
    await user.clear(screen.getByLabelText("Servings"));
    await user.type(screen.getByLabelText("Servings"), "6");
    await user.click(screen.getByRole("button", { name: /create meal/i }));

    expect(props.onAddMeal).toHaveBeenCalledWith("Spaghetti", 6);
  });

  it("goes straight on to the new meal's ingredients, cursor ready", async () => {
    const user = userEvent.setup();
    const curry = makeMeal({ id: 9, name: "Curry" });
    const { props, rerender } = renderTab(makeState({ meals: [tacos] }), "/meals");
    props.onAddMeal.mockImplementation(async () => curry);

    await user.click(screen.getByRole("button", { name: "New meal" }));
    expect(selection()).toBe("new");
    await user.type(screen.getByLabelText("Meal name"), "Curry{Enter}");

    await waitFor(() => expect(selection()).toBe("9"));
    // The cache now holds the meal, as it would after the API answers.
    rerender(<MealsTab {...props} state={makeState({ meals: [tacos, curry] })} />);
    expect(screen.getByRole("heading", { level: 2, name: "Curry" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ingredient")).toHaveFocus();
  });

  it("stays on the form if creating failed", async () => {
    const user = userEvent.setup();
    renderTab(makeState({ meals: [tacos] }), "/meals?meal=new");

    await user.type(screen.getByLabelText("Meal name"), "Tacos{Enter}");

    expect(selection()).toBe("new");
    expect(screen.getByLabelText("Meal name")).toHaveValue("Tacos");
  });

  describe("from a template", () => {
    const omelette = makeTemplate({ name: "Omelette" });
    const toast = makeTemplate({
      name: "Beans on Toast",
      ingredients: [{ name: "Bread", qty: 2, unit: "slices" }],
    });

    it("creates the meal and opens it", async () => {
      const user = userEvent.setup();
      const created = makeMeal({ id: 5, name: "Omelette" });
      const { props } = renderTab(makeState({ templates: [omelette] }));
      props.onAddFromTemplate.mockImplementation(async () => created);

      await user.click(screen.getByRole("button", { name: "Add Omelette" }));

      expect(props.onAddFromTemplate).toHaveBeenCalledWith("Omelette");
      await waitFor(() => expect(selection()).toBe("5"));
    });

    it("cannot add one already made (names match ignoring case, as in the API)", () => {
      renderTab(
        makeState({ templates: [omelette], meals: [makeMeal({ name: "omelette" })] }),
        "/meals?meal=new",
      );
      expect(screen.getByRole("button", { name: "Omelette (added)" })).toBeDisabled();
    });

    it("finds templates by name or by what's in them", async () => {
      const user = userEvent.setup();
      renderTab(makeState({ templates: [omelette, toast] }));

      await user.type(screen.getByLabelText("Search templates"), "bread");

      expect(screen.getByRole("button", { name: "Add Beans on Toast" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Omelette" })).not.toBeInTheDocument();
    });
  });
});

describe("changing a meal's details", () => {
  it("saves a new name and servings", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(makeState({ meals: [spaghetti] }), "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "Edit Spaghetti details" }));
    const name = screen.getByLabelText("Meal name");
    expect(name).toHaveFocus();
    await user.clear(name);
    await user.type(name, "Spag Bol");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(props.onUpdateMeal).toHaveBeenCalledWith(1, "Spag Bol", 4);
  });

  it("closes without saving on Escape", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(makeState({ meals: [spaghetti] }), "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "Edit Spaghetti details" }));
    await user.keyboard("{Escape}");

    expect(screen.queryByLabelText("Meal name")).not.toBeInTheDocument();
    expect(props.onUpdateMeal).not.toHaveBeenCalled();
  });
});

describe("deleting a meal", () => {
  const state = makeState({ meals: [spaghetti] });

  it("asks first, and deletes once confirmed", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "Delete Spaghetti" }));
    expect(props.onDeleteMeal).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(props.onDeleteMeal).toHaveBeenCalledWith(1);
  });

  it("does nothing when cancelled", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "Delete Spaghetti" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(props.onDeleteMeal).not.toHaveBeenCalled();
  });
});

describe("ingredients", () => {
  const state = makeState({
    meals: [spaghetti],
    ingredient_suggestions: [
      { name: "Pasta", unit: "g" },
      { name: "Onion", unit: "" },
      { name: "Garlic", unit: "cloves" },
    ],
  });

  it("requires a quantity greater than zero", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Ingredient"), "Onion");
    await user.type(screen.getByLabelText("Quantity"), "0");

    expect(screen.getByRole("button", { name: "Add ingredient" })).toBeDisabled();
    expect(props.onAddIngredient).not.toHaveBeenCalled();
  });

  it("adds with Enter, then is ready for the next one", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Ingredient"), "Bread");
    await user.type(screen.getByLabelText("Quantity"), "4");
    await user.type(screen.getByLabelText("Unit"), "slices{Enter}");

    // Not in the known list: anything typed is accepted.
    expect(props.onAddIngredient).toHaveBeenCalledWith(1, "Bread", 4, "slices");
    expect(screen.getByLabelText("Ingredient")).toHaveValue("");
    expect(screen.getByLabelText("Ingredient")).toHaveFocus();
  });

  it("suggests known ingredients and common units", () => {
    renderTab(state, "/meals?meal=1");

    const suggestions = (label: string) => {
      const input = screen.getByLabelText(label);
      const list = document.getElementById(input.getAttribute("list") ?? "");
      return Array.from(list?.querySelectorAll("option") ?? []).map((o) => o.value);
    };
    expect(suggestions("Ingredient")).toEqual(["Pasta", "Onion", "Garlic"]);
    expect(suggestions("Unit")).toContain("g");
  });

  it("fills in the unit a known ingredient is usually measured in", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Ingredient"), "garlic");
    expect(screen.getByLabelText("Unit")).toHaveValue("cloves");
    await user.type(screen.getByLabelText("Quantity"), "2{Enter}");

    expect(props.onAddIngredient).toHaveBeenCalledWith(1, "garlic", 2, "cloves");
  });

  it("clears a filled-in unit when the name stops matching", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Ingredient"), "Garlic bread");

    expect(screen.getByLabelText("Unit")).toHaveValue("");
  });

  it("leaves a unit the person typed alone", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Unit"), "tsp");
    await user.type(screen.getByLabelText("Ingredient"), "Garlic");

    expect(screen.getByLabelText("Unit")).toHaveValue("tsp");
  });

  it("says a counted ingredient needs no unit", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=1");

    await user.type(screen.getByLabelText("Ingredient"), "Onion");

    expect(screen.getByLabelText("Unit")).toHaveValue("");
    expect(screen.getByLabelText("Unit")).toHaveAttribute("placeholder", "none");
  });

  it("writes one of a counted unit in the singular", () => {
    renderTab(
      makeState({
        meals: [
          makeMeal({
            ingredients: [{ ingredient_id: 3, name: "Garlic", qty: 1, unit: "cloves" }],
          }),
        ],
      }),
      "/meals?meal=1",
    );

    expect(screen.getByRole("button", { name: "Edit Garlic" })).toHaveTextContent("1 clove");
  });

  it("removes one", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=1");

    await user.click(screen.getByRole("button", { name: "Remove Pasta" }));

    expect(props.onRemoveIngredient).toHaveBeenCalledWith(1, 7);
  });

  it("puts the cursor in the ingredient field of a meal with none", () => {
    renderTab(makeState({ meals: [tacos] }), "/meals?meal=2");
    expect(screen.getByLabelText("Ingredient")).toHaveFocus();
  });

  describe("editing an amount", () => {
    const withQty = (qty: number) =>
      makeState({
        meals: [
          makeMeal({
            id: 1,
            name: "Spaghetti",
            ingredients: [{ ingredient_id: 5, name: "Pasta", qty, unit: "g" }],
          }),
        ],
      });

    it("edits the current quantity, not the one first rendered", async () => {
      // Adding an ingredient again adds to it, so the amount can change
      // underneath the row. Fields seeded once at mount wrote the old one back.
      const user = userEvent.setup();
      const { props, rerender } = renderTab(withQty(200), "/meals?meal=1");

      rerender(<MealsTab {...props} state={withQty(400)} />);
      await user.click(screen.getByRole("button", { name: "Edit Pasta" }));
      expect(screen.getByLabelText("Quantity of Pasta")).toHaveFocus();
      await user.click(screen.getByRole("button", { name: "Save" }));

      expect(props.onUpdateIngredient).toHaveBeenCalledWith(1, 5, 400, "g");
    });

    it("cancels on Escape", async () => {
      const user = userEvent.setup();
      const { props } = renderTab(withQty(200), "/meals?meal=1");

      await user.click(screen.getByRole("button", { name: "Edit Pasta" }));
      await user.keyboard("{Escape}");

      expect(screen.queryByLabelText("Quantity of Pasta")).not.toBeInTheDocument();
      expect(props.onUpdateIngredient).not.toHaveBeenCalled();
    });
  });
});


describe("pasting a list", () => {
  const state = makeState({ meals: [spaghetti, tacos] });
  const lines = [
    parsed({ text: "500g beef mince", qty: 500, unit: "g", name: "Beef Mince" }),
    parsed({
      text: "2-3 garlic cloves, crushed",
      qty: 3,
      unit: "cloves",
      name: "Garlic",
      confidence: "medium",
      warnings: ["Read 2 to 3 as 3."],
    }),
    parsed({
      text: "Salt to taste",
      qty: null,
      name: "Salt",
      confidence: "low",
      warnings: ["No amount found."],
    }),
  ];

  async function readList(path = "/meals?meal=2", read = lines) {
    const user = userEvent.setup();
    const rendered = renderTab(state, path);
    rendered.props.onReadIngredients.mockResolvedValue(read);
    await user.click(screen.getByRole("button", { name: "Paste a list" }));
    await user.click(screen.getByLabelText("Paste the ingredient list"));
    await user.paste(read.map((line) => line.text).join("\n"));
    const button = read.length > 1 ? `Read ${read.length} lines` : "Read the list";
    await user.click(screen.getByRole("button", { name: button }));
    await screen.findByRole("heading", { name: "Check what was read" });
    return { user, ...rendered };
  }

  it("reads the pasted text and shows every line to check", async () => {
    const { props } = await readList();

    expect(props.onReadIngredients).toHaveBeenCalledWith(
      "500g beef mince\n2-3 garlic cloves, crushed\nSalt to taste",
    );
    expect(screen.getByLabelText("Ingredient on line 1")).toHaveValue("Beef Mince");
    expect(screen.getByLabelText("Quantity on line 2")).toHaveValue(3);
    expect(screen.getByLabelText("Unit on line 2")).toHaveValue("cloves");
    expect(screen.getByText("Read 2 to 3 as 3.")).toBeInTheDocument();
    // What each row came from, so a wrong reading is easy to spot.
    expect(screen.getByText("2-3 garlic cloves, crushed")).toBeInTheDocument();
  });

  it("will not save a line without an amount until one is given", async () => {
    const { user, props } = await readList();
    const save = screen.getByRole("button", { name: "Save 3 ingredients" });

    expect(save).toBeDisabled();
    expect(screen.getByLabelText("Quantity on line 3")).toBeInvalid();
    expect(screen.getByText(/1 line without an amount/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Quantity on line 3"), "5");
    await user.type(screen.getByLabelText("Unit on line 3"), "g");
    await user.click(save);

    expect(props.onReplaceIngredients).toHaveBeenCalledWith(2, [
      { name: "Beef Mince", qty: 500, unit: "g" },
      { name: "Garlic", qty: 3, unit: "cloves" },
      { name: "Salt", qty: 5, unit: "g" },
    ]);
  });

  it("removes every line without an amount in one go", async () => {
    const read = [
      ...lines,
      parsed({ text: "Oil for frying", qty: null, name: "Oil for frying", confidence: "low" }),
    ];
    const { user } = await readList("/meals?meal=2", read);

    expect(screen.getByText(/2 lines without an amount/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove all 2" }));

    expect(screen.queryByLabelText("Ingredient on line 3")).toBeNull();
    expect(screen.getByRole("button", { name: "Save 2 ingredients" })).toBeEnabled();
  });

  it("saves what is left after removing a line", async () => {
    const { user, props } = await readList();

    await user.click(screen.getByRole("button", { name: "Remove line 3" }));
    await user.clear(screen.getByLabelText("Ingredient on line 1"));
    await user.type(screen.getByLabelText("Ingredient on line 1"), "Pork Mince");
    await user.click(screen.getByRole("button", { name: "Save 2 ingredients" }));

    expect(props.onReplaceIngredients).toHaveBeenCalledWith(2, [
      { name: "Pork Mince", qty: 500, unit: "g" },
      { name: "Garlic", qty: 3, unit: "cloves" },
    ]);
  });

  it("adds to the ingredients already there unless told to replace them", async () => {
    const read = [parsed({ text: "2 onions", qty: 2, name: "Onion" })];
    const { user, props } = await readList("/meals?meal=1", read);

    await user.click(screen.getByRole("button", { name: "Save 1 ingredient" }));
    expect(props.onReplaceIngredients).toHaveBeenLastCalledWith(1, [
      { name: "Pasta", qty: 400, unit: "g" },
      { name: "Onion", qty: 2, unit: "" },
    ]);

    await user.click(screen.getByRole("checkbox", { name: /Replace the 1 ingredient/ }));
    await user.click(screen.getByRole("button", { name: "Save 1 ingredient" }));
    expect(props.onReplaceIngredients).toHaveBeenLastCalledWith(1, [
      { name: "Onion", qty: 2, unit: "" },
    ]);
  });

  it("goes back to the list of ingredients once saved", async () => {
    const { user, props } = await readList();
    props.onReplaceIngredients.mockResolvedValue(tacos);

    await user.click(screen.getByRole("button", { name: "Remove line 3" }));
    await user.click(screen.getByRole("button", { name: "Save 2 ingredients" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Check what was read" })).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "Paste a list" })).toBeInTheDocument();
  });

  it("keeps the preview if saving failed", async () => {
    const { user } = await readList();

    await user.click(screen.getByRole("button", { name: "Remove line 3" }));
    await user.click(screen.getByRole("button", { name: "Save 2 ingredients" }));

    expect(screen.getByRole("heading", { name: "Check what was read" })).toBeInTheDocument();
  });

  it("catches one ingredient listed in two units before the server refuses it", async () => {
    const read = [
      parsed({ text: "50 g butter", qty: 50, unit: "g", name: "Butter" }),
      parsed({ text: "1 tbsp butter", qty: 1, unit: "tbsp", name: "Butter" }),
    ];
    const { user } = await readList("/meals?meal=2", read);

    expect(screen.getByRole("button", { name: "Save 2 ingredients" })).toBeDisabled();
    expect(screen.getByText(/Butter is also listed in tbsp/)).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Unit on line 2"));
    await user.type(screen.getByLabelText("Unit on line 2"), "g");
    expect(screen.getByRole("button", { name: "Save 2 ingredients" })).toBeEnabled();
  });

  it("catches a clash with an ingredient already on the meal", async () => {
    const read = [parsed({ text: "1 cup pasta", qty: 1, unit: "cups", name: "Pasta" })];
    const { user } = await readList("/meals?meal=1", read);

    expect(screen.getByText(/Pasta is already on this meal in g/)).toBeInTheDocument();
    // Replacing removes the one it clashed with.
    await user.click(screen.getByRole("checkbox", { name: /Replace/ }));
    expect(screen.getByRole("button", { name: "Save 1 ingredient" })).toBeEnabled();
  });

  it("goes back to the text to change it", async () => {
    const { user } = await readList();

    await user.click(screen.getByRole("button", { name: "Back to the text" }));

    expect(screen.getByLabelText("Paste the ingredient list")).toHaveValue(
      "500g beef mince\n2-3 garlic cloves, crushed\nSalt to taste",
    );
  });

  it("stays on the text if reading failed", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=2");

    await user.click(screen.getByRole("button", { name: "Paste a list" }));
    await user.type(screen.getByLabelText("Paste the ingredient list"), "2 onions");
    await user.click(screen.getByRole("button", { name: "Read the list" }));

    expect(screen.getByLabelText("Paste the ingredient list")).toHaveValue("2 onions");
  });

  it("says when a list is longer than can be read at once", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=2");

    await user.click(screen.getByRole("button", { name: "Paste a list" }));
    await user.click(screen.getByLabelText("Paste the ingredient list"));
    await user.paste(Array.from({ length: 101 }, () => "1 onion").join("\n"));

    expect(screen.getByText(/That's 101 lines; paste up to 100/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Read 101 lines" })).toBeDisabled();
    expect(props.onReadIngredients).not.toHaveBeenCalled();
  });

  it("says which line is too long", async () => {
    const user = userEvent.setup();
    renderTab(state, "/meals?meal=2");

    await user.click(screen.getByRole("button", { name: "Paste a list" }));
    await user.click(screen.getByLabelText("Paste the ingredient list"));
    await user.paste(`2 onions\n${"x".repeat(201)}`);

    expect(screen.getByText("Line 2 is longer than 200 characters.")).toBeInTheDocument();
  });

  it("closes on Cancel without reading anything", async () => {
    const user = userEvent.setup();
    const { props } = renderTab(state, "/meals?meal=2");

    await user.click(screen.getByRole("button", { name: "Paste a list" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Paste the ingredient list")).toBeNull();
    expect(screen.getByLabelText("Ingredient")).toBeInTheDocument();
    expect(props.onReadIngredients).not.toHaveBeenCalled();
  });
});
