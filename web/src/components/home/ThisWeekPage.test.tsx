import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AppState, DayAssignment, GroceryLine, Meal, WeekPlan } from "@/api/types";
import { ThisWeekPage } from "@/components/home/ThisWeekPage";
import { makeMeal, makeState } from "@/test/factories";

const groceryLine: GroceryLine = {
  key: "",
  name: "",
  qty: 1,
  unit: "",
  display: "1",
  category: null,
  state: null,
  extra_id: null,
};

const WEEK = "2026-08-03"; // a Monday
const WEDNESDAY = "2026-08-05";

const tacos = makeMeal({
  id: 1,
  name: "Tacos",
  servings: 4,
  ingredients: [
    { ingredient_id: 10, name: "Beef mince", qty: 500, unit: "g" },
    { ingredient_id: 11, name: "Tortillas", qty: 8, unit: "" },
  ],
});
const curry = makeMeal({ id: 2, name: "Curry", servings: 6 });

const echo = async (week: string, days: DayAssignment[]): Promise<WeekPlan | null> => ({
  week_start: week,
  days,
});

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

function renderHome({
  today = WEDNESDAY,
  groceries = [],
  onCreateMeal = vi.fn(async (): Promise<Meal | null> => null),
  ...state
}: Partial<AppState> & {
  today?: string;
  groceries?: GroceryLine[] | null;
  onCreateMeal?: (name: string, servings: number) => Promise<Meal | null>;
} = {}) {
  const props = {
    state: makeState({ week_start: WEEK, meals: [tacos, curry], ...state }),
    today,
    groceries,
    onSave: vi.fn(echo),
    onCreateMeal,
  };
  return { ...render(<ThisWeekPage {...props} />), props };
}

const tonight = () => screen.getByRole("region", { name: /^Tonight/ });
const stat = (name: RegExp) => screen.getByRole("link", { name });
const strip = () => screen.getByRole("region", { name: "The week" });

/** The days sent in the most recent save, by day. */
function lastSaved(onSave: ReturnType<typeof vi.fn>): Record<string, DayAssignment> {
  const call = onSave.mock.lastCall;
  if (!call) throw new Error("Nothing has been saved.");
  return Object.fromEntries((call[1] as DayAssignment[]).map((d) => [d.day, d]));
}

describe("tonight", () => {
  it("shows tonight's meal and what it takes, scaled to the number cooked for", () => {
    renderHome({ plan: [{ day: "Wednesday", meal_id: 1, servings: 2 }] });

    const card = tonight();
    expect(card).toHaveAccessibleName(/Wed/);
    expect(card).toHaveTextContent("Tacos");
    expect(card).toHaveTextContent("Serves 2 · 2 ingredients");
    expect(card).toHaveTextContent("the recipe serves 4, scaled to 2");
    const lines = within(card).getAllByRole("listitem").map((li) => li.textContent);
    expect(lines).toEqual(["Beef mince250 g", "Tortillas4"]);
  });

  it("with nothing planned, choosing a meal plans tonight and saves it", async () => {
    const user = userEvent.setup();
    const { props } = renderHome();
    expect(tonight()).toHaveTextContent("Nothing planned yet");

    await user.click(screen.getByRole("button", { name: "Choose a meal for tonight" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Search meals" })).toHaveFocus(),
    );
    await user.keyboard("tac");
    await screen.findAllByRole("option", { name: /tac/i });
    await user.keyboard("{Enter}");

    expect(props.onSave).toHaveBeenCalledWith(WEEK, expect.any(Array));
    // At the recipe's own servings, on today's day of the week.
    expect(lastSaved(props.onSave).Wednesday).toEqual({
      day: "Wednesday",
      meal_id: 1,
      servings: 4,
    });
    expect(tonight()).toHaveTextContent("Tacos");
    expect(screen.getByRole("button", { name: "Change tonight's meal" })).toBeInTheDocument();
  });

  it("offers meals to plan in one click, those not had this week first", async () => {
    const user = userEvent.setup();
    const { props } = renderHome({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });

    const offers = within(tonight()).getAllByRole("button", { name: /^Plan .* for tonight$/ });
    expect(offers.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Plan Curry for tonight",
      "Plan Tacos for tonight",
    ]);

    await user.click(offers[0]);
    expect(lastSaved(props.onSave).Wednesday).toEqual({
      day: "Wednesday",
      meal_id: 2,
      servings: 6,
    });
    expect(tonight()).toHaveTextContent("Curry");
  });

  it("creates a meal typed in that does not exist yet, and plans it", async () => {
    const user = userEvent.setup();
    const laksa = makeMeal({ id: 7, name: "Laksa", servings: 4 });
    const onCreateMeal = vi.fn(async () => laksa);
    const { props } = renderHome({ onCreateMeal });

    await user.click(screen.getByRole("button", { name: "Choose a meal for tonight" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Search meals" })).toHaveFocus(),
    );
    await user.keyboard("Laksa");
    await user.click(await screen.findByRole("option", { name: /New meal/ }));

    expect(onCreateMeal).toHaveBeenCalledWith("Laksa", 4);
    await waitFor(() => expect(lastSaved(props.onSave).Wednesday).toMatchObject({ meal_id: 7 }));
  });

  it("points a meal with no ingredients to where they are added", () => {
    renderHome({ plan: [{ day: "Wednesday", meal_id: 2, servings: 6 }] });

    expect(within(tonight()).getByRole("link", { name: "Add its ingredients" })).toHaveAttribute(
      "href",
      "/meals?meal=2",
    );
  });

  it("shows tomorrow too, or leads to planning it", () => {
    const { unmount } = renderHome({ plan: [{ day: "Thursday", meal_id: 2, servings: 6 }] });
    expect(tonight()).toHaveTextContent(/Tomorrow.*Curry/);
    unmount();

    renderHome();
    expect(screen.getByRole("link", { name: "Nothing yet, plan Thursday" })).toHaveAttribute(
      "href",
      "/plan?day=Thursday",
    );
  });

  it("in any other week, is about its Monday instead", () => {
    renderHome({ today: "2026-08-12" });

    expect(screen.queryByRole("region", { name: /^Tonight/ })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^Monday/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose a meal for Monday" })).toBeInTheDocument();
  });

  it("has no tomorrow on a Sunday, the week's last day", () => {
    renderHome({ today: "2026-08-09" });

    expect(screen.getByRole("region", { name: /^Tonight/ })).not.toHaveTextContent("Tomorrow");
  });
});

describe("the numbers", () => {
  it("counts the nights planned, and leads to the first one left", () => {
    renderHome({
      plan: [
        { day: "Monday", meal_id: 1, servings: 4 },
        { day: "Tuesday", meal_id: 2, servings: 6 },
      ],
    });

    const nights = stat(/^Nights planned/);
    expect(nights).toHaveTextContent("2of 7");
    expect(nights).toHaveTextContent("Next: plan Wednesday");
    expect(nights).toHaveAttribute("href", "/plan?day=Wednesday");
  });

  it("says when every night is planned", () => {
    renderHome({
      plan: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
        (day) => ({ day: day as DayAssignment["day"], meal_id: 1, servings: 4 }),
      ),
    });

    expect(stat(/^Nights planned/)).toHaveTextContent("Every night is planned");
    expect(stat(/^Nights planned/)).toHaveAttribute("href", "/plan");
  });

  it("adds up the servings, a day without its own taking the recipe's", () => {
    renderHome({
      plan: [
        { day: "Monday", meal_id: 1, servings: null },
        { day: "Tuesday", meal_id: 1, servings: 2 },
      ],
    });

    expect(screen.getByText("Servings").parentElement).toHaveTextContent(
      "Servings6Across 1 different meal",
    );
  });

  it("counts what is on the grocery list, and waits while it loads", () => {
    const { unmount } = renderHome({ groceries: null });
    expect(stat(/^To buy/)).toHaveTextContent("…");
    expect(stat(/^To buy/)).toHaveAttribute("aria-busy", "true");
    unmount();

    renderHome({
      plan: [{ day: "Monday", meal_id: 1, servings: 4 }],
      groceries: [
        { ...groceryLine, key: "beef mince|g", name: "Beef mince", display: "500 g" },
        { ...groceryLine, key: "tortillas|", name: "Tortillas", display: "8" },
        // Neither is left to buy: one is in the basket, one already at home.
        { ...groceryLine, key: "salsa|", name: "Salsa", state: "basket" },
        { ...groceryLine, key: "cumin|", name: "Cumin", state: "have" },
      ],
    });
    expect(stat(/^To buy/)).toHaveTextContent("2items");
    expect(stat(/^To buy/)).toHaveAttribute("href", "/groceries");
  });

  it("keeps the week in every link", () => {
    window.history.replaceState(null, "", `/?week=${WEEK}`);
    renderHome();

    expect(stat(/^To buy/)).toHaveAttribute("href", `/groceries?week=${WEEK}`);
    expect(stat(/^Nights planned/)).toHaveAttribute("href", `/plan?week=${WEEK}&day=Monday`);
  });
});

describe("the week strip", () => {
  it("shows each day, and leads to that day's search on the plan", () => {
    renderHome({ plan: [{ day: "Monday", meal_id: 1, servings: 4 }] });

    const days = within(strip()).getAllByRole("link", { name: /day/ });
    expect(days).toHaveLength(7);
    expect(days[0]).toHaveAccessibleName("Monday 3 Tacos");
    expect(days[0]).toHaveAttribute("href", "/plan?day=Monday");
    expect(days[1]).toHaveTextContent("Not planned");
    expect(days[2]).toHaveAccessibleName(/^Wednesday 5, today/);
  });
});
