import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { usePlanner } from "@/hooks/usePlanner";
import { makeMeal, makeState } from "@/test/factories";

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  api: {
    getState: vi.fn(),
    getPlan: vi.fn(),
    setPlan: vi.fn(),
    deleteMeal: vi.fn(),
    getGroceryList: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

const plan = (mealId: number | null) => [
  { day: "Monday" as const, meal_id: mealId, servings: mealId ? 4 : null },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocked.getState.mockResolvedValue(
    makeState({
      week_start: "2026-08-24",
      meals: [makeMeal({ id: 1, name: "Spaghetti" })],
      plan: plan(1),
    }),
  );
  mocked.getPlan.mockImplementation(async (week: string) => ({
    week_start: week,
    days: plan(null),
  }));
});

/** Render, and wait for the initial bootstrap to land. */
async function renderPlanner() {
  const view = renderHook(() => usePlanner());
  await waitFor(() => expect(view.result.current.state).not.toBeNull());
  return view;
}

describe("loading a week", () => {
  it("fetches the whole app state once, on first load", async () => {
    await renderPlanner();

    expect(mocked.getState).toHaveBeenCalledTimes(1);
    expect(mocked.getPlan).not.toHaveBeenCalled();
  });

  it("fetches only the plan when the week changes", async () => {
    // Meals, templates and ingredient names do not vary by week, so
    // refetching them on every arrow click was three wasted queries.
    const { result } = await renderPlanner();

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() =>
      expect(mocked.getPlan).toHaveBeenCalledWith("2026-08-31"),
    );

    expect(mocked.getState).toHaveBeenCalledTimes(1);
  });

  it("moves week_start with the plan", async () => {
    // Patching only `plan` left the heading naming the week we had left.
    const { result } = await renderPlanner();

    act(() => result.current.setWeek("2026-08-31"));

    await waitFor(() =>
      expect(result.current.state?.week_start).toBe("2026-08-31"),
    );
  });

  it("keeps the meals it already has", async () => {
    const { result } = await renderPlanner();

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalled());

    expect(result.current.state?.meals).toHaveLength(1);
  });
});

describe("weeks already visited", () => {
  it("serves them from memory rather than the network", async () => {
    const { result } = await renderPlanner();

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(1));

    act(() => result.current.setWeek("2026-08-24"));
    await waitFor(() =>
      expect(result.current.state?.week_start).toBe("2026-08-24"),
    );

    expect(mocked.getPlan).toHaveBeenCalledTimes(1);
  });

  it("shows a plan saved since, not the one first fetched", async () => {
    const { result } = await renderPlanner();
    mocked.setPlan.mockResolvedValue({
      week_start: "2026-08-24",
      days: plan(1),
    });

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(1));
    await act(() => result.current.savePlan(plan(1)));

    act(() => result.current.setWeek("2026-08-24"));
    act(() => result.current.setWeek("2026-08-31"));

    await waitFor(() => expect(result.current.state?.plan[0].meal_id).toBe(1));
    // Still one fetch: the cache was corrected in place, not invalidated.
    expect(mocked.getPlan).toHaveBeenCalledTimes(1);
  });

  it("refetches after a delete, which unassigns the meal everywhere", async () => {
    const { result } = await renderPlanner();
    mocked.deleteMeal.mockResolvedValue(undefined);

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(1));
    await act(() => result.current.deleteMeal(1));

    act(() => result.current.setWeek("2026-08-24"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(2));
  });
});

describe("the grocery list", () => {
  const lines = [{ name: "Pasta", qty: 400, unit: "g", display: "400 g" }];

  it("belongs to the week it was generated for", async () => {
    const { result } = await renderPlanner();
    mocked.getGroceryList.mockResolvedValue(lines);

    await act(() => result.current.generateGroceryList());
    expect(result.current.grocery).toEqual(lines);

    // A list for last week must not be shown as if it were this week's.
    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() =>
      expect(result.current.state?.week_start).toBe("2026-08-31"),
    );
    expect(result.current.grocery).toBeNull();
  });

  it("comes back when you return to that week", async () => {
    const { result } = await renderPlanner();
    mocked.getGroceryList.mockResolvedValue(lines);

    await act(() => result.current.generateGroceryList());
    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(result.current.grocery).toBeNull());

    act(() => result.current.setWeek("2026-08-24"));

    await waitFor(() => expect(result.current.grocery).toEqual(lines));
    expect(mocked.getGroceryList).toHaveBeenCalledTimes(1);
  });
});
