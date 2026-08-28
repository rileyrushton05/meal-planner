import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DayAssignment } from "../api/types";
import { makeMeal, makeState } from "../test/factories";
import { WeeklyPlanTab } from "./WeeklyPlanTab";

const spaghetti = makeMeal({ id: 1, name: "Spaghetti", servings: 4 });
const stirFry = makeMeal({ id: 2, name: "Chicken Stir Fry", servings: 2 });

function renderTab(overrides = {}) {
  const props = {
    state: makeState({ meals: [spaghetti, stirFry] }),
    busy: false,
    onSave: vi.fn(),
    onCopyPrevious: vi.fn(),
    ...overrides,
  };
  return { ...render(<WeeklyPlanTab {...props} />), props };
}

describe("editing the plan", () => {
  it("keeps changes local until Save is pressed", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.selectOptions(screen.getByLabelText("Monday"), "1");

    // The whole point of the draft: no network call from changing a dropdown.
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("submits every day, including the ones left unset", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.selectOptions(screen.getByLabelText("Monday"), "1");
    await user.click(screen.getByRole("button", { name: "Set Weekly Plan" }));

    const days = props.onSave.mock.calls[0][0] as DayAssignment[];
    expect(days).toHaveLength(7);
    expect(days.find((d) => d.day === "Monday")?.meal_id).toBe(1);
    expect(days.find((d) => d.day === "Tuesday")?.meal_id).toBeNull();
  });

  it("defaults servings to the recipe's own size when a meal is picked", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.selectOptions(screen.getByLabelText("Tuesday"), "2");
    await user.click(screen.getByRole("button", { name: "Set Weekly Plan" }));

    const days = props.onSave.mock.calls[0][0] as DayAssignment[];
    expect(days.find((d) => d.day === "Tuesday")?.servings).toBe(2);
  });

  it("clears servings when a day is unset", async () => {
    const user = userEvent.setup();
    const plan = [{ day: "Monday", meal_id: 1, servings: 4 }];
    const { props } = renderTab({
      state: makeState({ meals: [spaghetti, stirFry], plan }),
    });

    await user.selectOptions(screen.getByLabelText("Monday"), "");
    await user.click(screen.getByRole("button", { name: "Set Weekly Plan" }));

    const days = props.onSave.mock.calls[0][0] as DayAssignment[];
    const monday = days.find((d) => d.day === "Monday");
    expect(monday?.meal_id).toBeNull();
    expect(monday?.servings).toBeNull();
  });
});

describe("re-seeding the draft", () => {
  it("adopts a new plan returned by the server", () => {
    // Regression test: the draft was re-seeded inside an effect, which
    // renders once with stale data before correcting. It is now derived
    // during render.
    const meals = [spaghetti, stirFry];
    const { rerender } = render(
      <WeeklyPlanTab
        state={makeState({ meals })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Monday")).toHaveValue("");

    rerender(
      <WeeklyPlanTab
        state={makeState({
          meals,
          plan: [{ day: "Monday", meal_id: 1, servings: 4 }],
        })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Monday")).toHaveValue("1");
  });

  it("does not discard an in-progress edit when unrelated state changes", async () => {
    const user = userEvent.setup();
    const meals = [spaghetti, stirFry];
    const plan: DayAssignment[] = [];
    const { rerender } = render(
      <WeeklyPlanTab
        state={makeState({ meals, plan })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Wednesday"), "2");

    // A meal being added elsewhere must not wipe the day the user just set.
    rerender(
      <WeeklyPlanTab
        state={makeState({ meals: [...meals, makeMeal({ id: 3, name: "Tacos" })], plan })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Wednesday")).toHaveValue("2");
  });
});

describe("week overview", () => {
  it("shows an em dash for days with no meal", () => {
    renderTab();
    expect(screen.getAllByText("—").length).toBe(7);
  });

  it("shows the meal and its planned servings", () => {
    renderTab({
      state: makeState({
        meals: [spaghetti, stirFry],
        plan: [{ day: "Monday", meal_id: 1, servings: 2 }],
      }),
    });

    expect(screen.getByText("Spaghetti", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("2 servings")).toBeInTheDocument();
  });

  it("uses the singular for one serving", () => {
    renderTab({
      state: makeState({
        meals: [spaghetti],
        plan: [{ day: "Monday", meal_id: 1, servings: 1 }],
      }),
    });

    expect(screen.getByText("1 serving")).toBeInTheDocument();
  });
});

describe("empty state", () => {
  it("asks for a meal before offering the form", () => {
    renderTab({ state: makeState({ meals: [] }) });

    expect(screen.getByText(/add a meal first/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Set Weekly Plan" }),
    ).not.toBeInTheDocument();
  });
});
