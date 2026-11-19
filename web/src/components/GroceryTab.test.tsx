import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Category, GroceryLine, GroceryList, GroceryUsual } from "@/api/types";
import { type GroceryActions, GroceryTab } from "@/components/GroceryTab";
import { DEFAULT_AISLE_ORDER } from "@/lib/aisles";

const WEEK = "2026-08-03";

function line(name: string, display: string, more: Partial<GroceryLine> = {}): GroceryLine {
  return {
    key: `${name.toLowerCase()}|`,
    name,
    qty: 1,
    unit: "",
    display,
    category: null,
    state: null,
    extra_id: null,
    ...more,
  };
}

const lines: GroceryLine[] = [
  line("Beef Mince", "1.5 kg"),
  line("Onion", "2"),
  line("Pasta", "400 g"),
];

function listOf(of: GroceryLine[], more: Partial<GroceryList> = {}): GroceryList {
  return { week_start: WEEK, lines: of, usuals: [], aisle_order: DEFAULT_AISLE_ORDER, ...more };
}

beforeEach(() => {
  window.history.replaceState(null, "", "/groceries");
});

/**
 * The page as the app runs it: the list held above it, and a tick or a
 * new aisle order applied there, as the planner hook does, so what a test
 * clicks shows up as it would.
 */
function renderList(
  props: { list?: GroceryList | null; plannedDays?: number; pending?: boolean } = {},
  overrides: Partial<GroceryActions> = {},
) {
  const actions: GroceryActions = {
    onCheck: vi.fn(),
    onEmptyBasket: vi.fn(),
    onAddExtra: vi.fn(async () => true),
    onRemoveExtra: vi.fn(),
    onKeepExtra: vi.fn(),
    onAddUsuals: vi.fn(),
    onAddUsual: vi.fn(async () => true),
    onRemoveUsual: vi.fn(),
    onAisleOrder: vi.fn(),
    ...overrides,
  };

  function Harness() {
    const [list, setList] = useState(props.list === undefined ? listOf(lines) : props.list);
    return (
      <GroceryTab
        weekStart={WEEK}
        list={list}
        plannedDays={props.plannedDays ?? 2}
        pending={props.pending ?? false}
        {...actions}
        onCheck={(key, state) => {
          actions.onCheck(key, state);
          setList((current) =>
            current && {
              ...current,
              lines: current.lines.map((l) => (l.key === key ? { ...l, state } : l)),
            },
          );
        }}
        onEmptyBasket={() => {
          actions.onEmptyBasket();
          setList((current) =>
            current && {
              ...current,
              lines: current.lines.map((l) => (l.state === "basket" ? { ...l, state: null } : l)),
            },
          );
        }}
        onAisleOrder={(order: Category[]) => {
          actions.onAisleOrder(order);
          setList((current) => current && { ...current, aisle_order: order });
        }}
      />
    );
  }

  render(<Harness />);
  return actions;
}

const toGet = () => screen.getByRole("region", { name: /^To get/ });
const basket = () => screen.queryByRole("region", { name: /^In the basket/ });
const atHome = () => screen.queryByRole("region", { name: /^Already have/ });
const names = (region: HTMLElement) =>
  within(region)
    .getAllByRole("checkbox")
    .map((box) => box.closest("label")?.textContent);
const count = () => screen.getByText(/in the basket$/).parentElement;
const menuFor = (name: string) => screen.getByRole("button", { name: `More for ${name}` });

describe("before there is a list", () => {
  it("waits while it loads", () => {
    renderList({ list: null });
    expect(screen.getByRole("status")).toHaveTextContent("Loading the list…");
  });

  it("leads to planning when nothing is planned, and still takes extras", () => {
    renderList({ list: listOf([]), plannedDays: 0 });
    expect(screen.getByText(/Nothing is planned this week/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plan the week" })).toHaveAttribute("href", "/plan");
    expect(screen.getByRole("textbox", { name: "Add something else" })).toBeInTheDocument();
  });

  it("leads to the meals when what is planned has no ingredients", () => {
    renderList({ list: listOf([]), plannedDays: 3 });
    expect(screen.getByText(/have no ingredients yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add ingredients" })).toHaveAttribute("href", "/meals");
  });
});

describe("shopping", () => {
  it("lists everything to get, with the amounts the API formatted", () => {
    renderList();

    // 1500 g arrives already turned into 1.5 kg by the domain layer.
    expect(names(toGet())).toEqual(["Beef Mince 1.5 kg", "Onion 2", "Pasta 400 g"]);
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).not.toBeChecked();
    expect(count()).toHaveTextContent("0of 3 in the basket");
    expect(basket()).not.toBeInTheDocument();
  });

  it("shows what was already ticked, on this device or another", () => {
    renderList({ list: listOf([lines[0], { ...lines[1], state: "basket" }, lines[2]]) });

    expect(names(basket()!)).toEqual(["Onion 2"]);
    expect(count()).toHaveTextContent("1of 3 in the basket");
  });

  it("drops a ticked item into the basket, saving the tick by the line's key", async () => {
    const user = userEvent.setup();
    const actions = renderList();

    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));

    expect(actions.onCheck).toHaveBeenCalledWith("beef mince|", "basket");
    expect(names(toGet())).toEqual(["Onion 2", "Pasta 400 g"]);
    expect(names(basket()!)).toEqual(["Beef Mince 1.5 kg"]);
    expect(count()).toHaveTextContent("1of 3 in the basket");
  });

  it("takes an item back out of the basket", async () => {
    const user = userEvent.setup();
    const actions = renderList();

    await user.click(screen.getByRole("checkbox", { name: "Onion 2" }));
    await user.click(screen.getByRole("checkbox", { name: "Onion 2" }));

    expect(actions.onCheck).toHaveBeenLastCalledWith("onion|", null);
    expect(names(toGet())).toEqual(["Beef Mince 1.5 kg", "Onion 2", "Pasta 400 g"]);
    expect(basket()).not.toBeInTheDocument();
  });

  it("keeps keyboard focus on the list: on the item that took the ticked one's place", async () => {
    const user = userEvent.setup();
    renderList();

    screen.getByRole("checkbox", { name: "Onion 2" }).focus();
    await user.keyboard(" ");
    expect(screen.getByRole("checkbox", { name: "Pasta 400 g" })).toHaveFocus();

    // The last one left: focus follows it into the basket.
    await user.keyboard(" ");
    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));
    expect(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" })).toHaveFocus();
    expect(screen.getByText("That's everything. Enjoy the cooking.")).toBeInTheDocument();
  });

  it("starts again with an empty basket", async () => {
    const user = userEvent.setup();
    const actions = renderList();
    await user.click(screen.getByRole("checkbox", { name: "Pasta 400 g" }));

    await user.click(screen.getByRole("button", { name: "Start again" }));

    expect(actions.onEmptyBasket).toHaveBeenCalledOnce();
    expect(count()).toHaveTextContent("0of 3 in the basket");
    expect(screen.queryByRole("button", { name: "Start again" })).not.toBeInTheDocument();
  });
});

describe("already at home", () => {
  it("sets a line aside, out of the count, and brings it back", async () => {
    const user = userEvent.setup();
    const actions = renderList();

    await user.click(menuFor("Onion"));
    await user.click(await screen.findByRole("menuitem", { name: "Already have it" }));

    expect(actions.onCheck).toHaveBeenCalledWith("onion|", "have");
    expect(names(toGet())).toEqual(["Beef Mince 1.5 kg", "Pasta 400 g"]);
    expect(within(atHome()!).getByText("Onion")).toBeInTheDocument();
    expect(count()).toHaveTextContent("0of 2 in the basket");

    await user.click(screen.getByRole("button", { name: "Need Onion after all" }));

    expect(actions.onCheck).toHaveBeenLastCalledWith("onion|", null);
    expect(atHome()).not.toBeInTheDocument();
    expect(count()).toHaveTextContent("0of 3 in the basket");
  });
});

describe("extras", () => {
  const milk = line("Milk", "2 L", { key: "+milk", extra_id: 7, category: "dairy" });

  it("adds what is typed, clearing the field once it is on the list", async () => {
    const user = userEvent.setup();
    const actions = renderList();

    await user.type(screen.getByRole("textbox", { name: "Add something else" }), "2 L milk");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(actions.onAddExtra).toHaveBeenCalledWith("2 L milk");
    expect(screen.getByRole("textbox", { name: "Add something else" })).toHaveValue("");
  });

  it("keeps what was typed when adding fails, to fix", async () => {
    const user = userEvent.setup();
    renderList({}, { onAddExtra: vi.fn(async () => false) });

    await user.type(screen.getByRole("textbox", { name: "Add something else" }), "2 kg");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(screen.getByRole("textbox", { name: "Add something else" })).toHaveValue("2 kg");
  });

  it("marks an extra as one, and its menu keeps it as a usual or removes it", async () => {
    const user = userEvent.setup();
    const actions = renderList({ list: listOf([...lines, milk]) });

    expect(screen.getByRole("checkbox", { name: "Milk extra 2 L" })).toBeInTheDocument();

    await user.click(menuFor("Milk"));
    await user.click(await screen.findByRole("menuitem", { name: "Keep as a usual" }));
    expect(actions.onKeepExtra).toHaveBeenCalledWith(7);

    await user.click(menuFor("Milk"));
    await user.click(await screen.findByRole("menuitem", { name: "Remove from the list" }));
    expect(actions.onRemoveExtra).toHaveBeenCalledWith(7);
  });

  it("says when an extra is already one of the usuals", async () => {
    const user = userEvent.setup();
    const usuals: GroceryUsual[] = [{ id: 1, name: "Milk", qty: 2, unit: "L", display: "2 L" }];
    renderList({ list: listOf([...lines, milk], { usuals }) });

    await user.click(menuFor("Milk"));

    expect(await screen.findByRole("menuitem", { name: "One of your usuals" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("gives a meal's line no menu once it is in the basket", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(screen.getByRole("checkbox", { name: "Onion 2" }));

    expect(screen.queryByRole("button", { name: "More for Onion" })).not.toBeInTheDocument();
  });
});

describe("usuals", () => {
  const usuals: GroceryUsual[] = [
    { id: 1, name: "Bread", qty: null, unit: "", display: "" },
    { id: 2, name: "Milk", qty: 2, unit: "L", display: "2 L" },
  ];

  it("adds them all to the week in one click", async () => {
    const user = userEvent.setup();
    const actions = renderList({ list: listOf(lines, { usuals }) });

    await user.click(screen.getByRole("button", { name: "Add my 2 usuals" }));

    expect(actions.onAddUsuals).toHaveBeenCalledOnce();
  });

  it("offers only the ones not on the list yet", () => {
    const milk = line("Milk", "2 L", { key: "+milk", extra_id: 7 });
    renderList({ list: listOf([...lines, milk], { usuals }) });

    expect(screen.getByRole("button", { name: "Add the other usual" })).toBeInTheDocument();
  });

  it("are looked after in their own dialog", async () => {
    const user = userEvent.setup();
    const actions = renderList({ list: listOf(lines, { usuals }) });

    await user.click(screen.getByRole("button", { name: /^My usuals/ }));
    const dialog = await screen.findByRole("dialog", { name: "My usuals" });

    expect(within(dialog).getByText("Bread")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Remove Bread from your usuals" }));
    expect(actions.onRemoveUsual).toHaveBeenCalledWith(1);

    await user.type(within(dialog).getByRole("textbox", { name: "Add a usual" }), "dog food");
    await user.click(within(dialog).getByRole("button", { name: "Add" }));
    expect(actions.onAddUsual).toHaveBeenCalledWith("dog food");
  });
});

describe("aisles", () => {
  // Out of order on purpose: the page, not only the server, keeps the shop's order.
  const shop: GroceryLine[] = [
    line("Pasta", "400 g", { category: "pantry" }),
    line("Dragon Fruit", "1"),
    line("Onion", "2", { category: "produce" }),
    line("Beef Mince", "500 g", { category: "meat" }),
    line("Garlic", "2 cloves", { category: "produce" }),
  ];
  const aisle = (name: string) => screen.getByRole("group", { name });
  const headings = () =>
    within(toGet())
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);

  it("groups what is left to get by aisle, in the order a shop is walked", () => {
    renderList({ list: listOf(shop) });

    expect(headings()).toEqual(["Fruit & veg", "Meat & seafood", "Pantry", "Other"]);
    expect(names(aisle("Fruit & veg"))).toEqual(["Onion 2", "Garlic 2 cloves"]);
    expect(names(aisle("Other"))).toEqual(["Dragon Fruit 1"]);
  });

  it("follows the person's own aisle order", () => {
    const order: Category[] = ["pantry", "meat", "produce", "dairy", "bakery", "frozen"];
    renderList({ list: listOf(shop, { aisle_order: order }) });

    expect(headings()).toEqual(["Pantry", "Meat & seafood", "Fruit & veg", "Other"]);
  });

  it("drops an aisle once everything in it is in the basket", async () => {
    const user = userEvent.setup();
    renderList({ list: listOf(shop) });

    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 500 g" }));

    expect(screen.queryByRole("group", { name: "Meat & seafood" })).not.toBeInTheDocument();
    expect(names(basket()!)).toEqual(["Beef Mince 500 g"]);
  });

  it("moves focus to the next item along the shop, across aisles", async () => {
    const user = userEvent.setup();
    renderList({ list: listOf(shop) });

    screen.getByRole("checkbox", { name: "Garlic 2 cloves" }).focus();
    await user.keyboard(" ");

    expect(screen.getByRole("checkbox", { name: "Beef Mince 500 g" })).toHaveFocus();
  });

  it("shows no headings when everything is in one aisle", () => {
    renderList({ list: listOf(shop.filter((l) => l.category === "produce")) });

    expect(within(toGet()).queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("are put in the shop's order with up and down, saved only on Save", async () => {
    const user = userEvent.setup();
    const actions = renderList({ list: listOf(shop) });

    await user.click(screen.getByRole("button", { name: "Aisle order" }));
    const dialog = await screen.findByRole("dialog", { name: "Aisle order" });
    expect(within(dialog).getByRole("button", { name: "Move Fruit & veg up" })).toBeDisabled();
    for (let i = 0; i < 4; i++) {
      await user.click(within(dialog).getByRole("button", { name: "Move Pantry up" }));
    }
    expect(actions.onAisleOrder).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(actions.onAisleOrder).toHaveBeenCalledWith([
      "pantry",
      "produce",
      "meat",
      "dairy",
      "bakery",
      "frozen",
    ]);
    expect(headings()).toEqual(["Pantry", "Fruit & veg", "Meat & seafood", "Other"]);
  });

  it("can go back to the usual order", async () => {
    const user = userEvent.setup();
    const order: Category[] = ["frozen", "pantry", "bakery", "dairy", "meat", "produce"];
    const actions = renderList({ list: listOf(shop, { aisle_order: order }) });

    await user.click(screen.getByRole("button", { name: "Aisle order" }));
    const dialog = await screen.findByRole("dialog", { name: "Aisle order" });
    await user.click(within(dialog).getByRole("button", { name: "Back to the usual order" }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(actions.onAisleOrder).toHaveBeenCalledWith(DEFAULT_AISLE_ORDER);
  });

  it("copies under aisle headings, in the person's order", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const order: Category[] = ["meat", "produce", "dairy", "bakery", "pantry", "frozen"];
    renderList({ list: listOf(shop, { aisle_order: order }) });

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith(
      [
        "Meat & seafood\n- Beef Mince: 500 g",
        "Fruit & veg\n- Onion: 2\n- Garlic: 2 cloves",
        "Pantry\n- Pasta: 400 g",
        "Other\n- Dragon Fruit: 1",
      ].join("\n\n"),
    );
  });
});

describe("sharing", () => {
  it("copies what is left to get", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    renderList({
      list: listOf([...lines, line("Bin bags", "", { key: "+bin bags", extra_id: 3 })]),
    });
    await user.click(screen.getByRole("checkbox", { name: "Beef Mince 1.5 kg" }));

    await user.click(screen.getByRole("button", { name: "Copy what's left" }));

    expect(writeText).toHaveBeenCalledWith("- Onion: 2\n- Pasta: 400 g\n- Bin bags");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
