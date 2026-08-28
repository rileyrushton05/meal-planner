import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DayAssignment } from "@/api/types";
import { WeeklyPlanTab } from "@/components/WeeklyPlanTab";
import { makeMeal, makeState } from "@/test/factories";
import { chooseOption } from "@/test/select";

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
  it("keeps changes local until the plan is saved", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await chooseOption(user, "Monday", "Spaghetti");

    // The point of the draft: choosing a meal makes no network call.
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("submits every day, including the ones left unset", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await chooseOption(user, "Monday", "Spaghetti");
    await user.click(screen.getByRole("button", { name: "Save plan" }));

    const days = props.onSave.mock.calls[0][0] as DayAssignment[];
    expect(days).toHaveLength(7);
    expect(days.find((d) => d.day === "Monday")?.meal_id).toBe(1);
    expect(days.find((d) => d.day === "Tuesday")?.meal_id).toBeNull();
  });

  it("defaults servings to the recipe's own size", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await chooseOption(user, "Tuesday", "Chicken Stir Fry");
    await user.click(screen.getByRole("button", { name: "Save plan" }));

    const days = props.onSave.mock.calls[0][0] as DayAssignment[];
    expect(days.find((d) => d.day === "Tuesday")?.servings).toBe(2);
  });

  it("clears servings when a day is unset", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({
      state: makeState({
        meals: [spaghetti, stirFry],
        plan: [{ day: "Monday", meal_id: 1, servings: 4 }],
      }),
    });

    await chooseOption(user, "Monday", "No meal");
    await user.click(screen.getByRole("button", { name: "Save plan" }));

    const monday = (props.onSave.mock.calls[0][0] as DayAssignment[]).find(
      (d) => d.day === "Monday",
    );
    expect(monday?.meal_id).toBeNull();
    expect(monday?.servings).toBeNull();
  });

  it("disables Save until something changes", async () => {
    const user = userEvent.setup();
    renderTab();

    expect(screen.getByRole("button", { name: "Save plan" })).toBeDisabled();

    await chooseOption(user, "Monday", "Spaghetti");

    expect(screen.getByRole("button", { name: "Save plan" })).toBeEnabled();
  });
});

describe("re-seeding the draft", () => {
  const meals = [spaghetti, stirFry];

  it("adopts a new plan returned by the server", () => {
    // Regression test: the draft was re-seeded inside an effect, which
    // rendered once with stale data before correcting.
    const { rerender } = render(
      <WeeklyPlanTab
        state={makeState({ meals })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );
    expect(screen.getByRole("combobox", { name: "Monday" })).toHaveTextContent(
      "No meal",
    );

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

    expect(screen.getByRole("combobox", { name: "Monday" })).toHaveTextContent(
      "Spaghetti",
    );
  });

  it("does not discard an in-progress edit when unrelated state changes", async () => {
    const user = userEvent.setup();
    const plan: DayAssignment[] = [];
    const { rerender } = render(
      <WeeklyPlanTab
        state={makeState({ meals, plan })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    await chooseOption(user, "Wednesday", "Chicken Stir Fry");

    // A meal added elsewhere must not wipe the day just set.
    rerender(
      <WeeklyPlanTab
        state={makeState({
          meals: [...meals, makeMeal({ id: 3, name: "Tacos" })],
          plan,
        })}
        busy={false}
        onSave={vi.fn()}
        onCopyPrevious={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("combobox", { name: "Wednesday" }),
    ).toHaveTextContent("Chicken Stir Fry");
  });
});

describe("the week grid", () => {
  it("shows a card for every day", () => {
    renderTab();
    expect(screen.getAllByRole("combobox")).toHaveLength(7);
  });

  it("only offers a servings field once a meal is assigned", () => {
    renderTab({
      state: makeState({
        meals: [spaghetti],
        plan: [{ day: "Monday", meal_id: 1, servings: 2 }],
      }),
    });

    expect(screen.getByLabelText("Serves")).toHaveValue(2);
  });

  it("copies the previous week on request", async () => {
    const user = userEvent.setup();
    const { props } = renderTab();

    await user.click(screen.getByRole("button", { name: /copy previous/i }));

    expect(props.onCopyPrevious).toHaveBeenCalled();
  });
});

describe("empty state", () => {
  it("asks for a meal before showing the grid", () => {
    renderTab({ state: makeState({ meals: [] }) });

    expect(screen.getByText(/add a meal first/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});


describe("the day dropdown", () => {
  it("shows the meal's name, not its id", async () => {
    // Regression test: Base UI's Select.Value renders the raw value, so an
    // id-valued select displayed "1" where the meal name belonged.
    const user = userEvent.setup();
    renderTab();

    await chooseOption(user, "Monday", "Spaghetti");

    const trigger = screen.getByRole("combobox", { name: "Monday" });
    expect(trigger).toHaveTextContent("Spaghetti");
    expect(trigger).not.toHaveTextContent(/^\d/);
  });
});
