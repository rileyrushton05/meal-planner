import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/api/client";
import { clearLastVisit, restoreLastVisit } from "@/api/persistence";
import { createQueryClient } from "@/api/queryClient";
import type { GroceryList } from "@/api/types";
import { usePlanner } from "@/hooks/usePlanner";
import { makeMeal, makeState } from "@/test/factories";
import { saveLastVisit } from "@/test/lastVisit";

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  api: {
    getState: vi.fn(),
    getPlan: vi.fn(),
    setPlan: vi.fn(),
    deleteMeal: vi.fn(),
    getGroceries: vi.fn(),
    setGroceryCheck: vi.fn(),
    addExtra: vi.fn(),
    setAisleOrder: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

afterEach(() => {
  vi.useRealTimers();
});

const plan = (mealId: number | null) => [
  { day: "Monday" as const, meal_id: mealId, servings: mealId ? 4 : null },
];

beforeEach(() => {
  vi.clearAllMocks();
  // The week lives in the URL, and jsdom keeps it between tests.
  window.history.replaceState(null, "", "/");
  // The hook starts on the Monday of the current real week, and these tests
  // assert against a fixed one. Without pinning the clock they only passed
  // during the week of 24 August 2026, and quietly stopped meaning anything
  // after it. shouldAdvanceTime keeps waitFor working.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-08-26T09:00:00"));
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

/** Render with a fresh cache, and wait for the initial bootstrap to land. */
async function renderPlanner(options: Parameters<typeof usePlanner>[0] = {}) {
  const client = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
  const view = renderHook(() => usePlanner(options), { wrapper });
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
    // The server replies with the week it saved, which is the week sent.
    mocked.setPlan.mockImplementation(async (week: string) => ({
      week_start: week,
      days: plan(1),
    }));

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(1));
    await act(() => result.current.savePlan("2026-08-31", plan(1)));

    act(() => result.current.setWeek("2026-08-24"));
    act(() => result.current.setWeek("2026-08-31"));

    await waitFor(() => expect(result.current.state?.plan[0].meal_id).toBe(1));
    // Still one fetch: the cache was corrected in place, not invalidated.
    expect(mocked.getPlan).toHaveBeenCalledTimes(1);
  });

  it("saves the week it is told to, whatever week is on screen", async () => {
    const { result } = await renderPlanner();
    mocked.setPlan.mockImplementation(async (week: string) => ({ week_start: week, days: [] }));

    act(() => result.current.setWeek("2026-08-31"));
    await act(() => result.current.savePlan("2026-08-24", []));

    expect(mocked.setPlan).toHaveBeenCalledWith("2026-08-24", []);
  });

  it("resolves a failed save with null, and reports why", async () => {
    const { result } = await renderPlanner();
    mocked.setPlan.mockRejectedValue(new ApiError(404, "No meal with id 9."));

    let saved: unknown = "not yet";
    await act(async () => {
      saved = await result.current.savePlan("2026-08-24", []);
    });

    expect(saved).toBeNull();
    expect(result.current.error).toBe("No meal with id 9.");
  });

  it("files a slow save under the week it was saved for", async () => {
    // Switching week while a save is in flight must not put that plan on
    // the week now on screen.
    const { result } = await renderPlanner();
    let finishSave!: (saved: { week_start: string; days: ReturnType<typeof plan> }) => void;
    mocked.setPlan.mockReturnValue(
      new Promise((resolve) => {
        finishSave = resolve;
      }),
    );

    act(() => {
      void result.current.savePlan("2026-08-24", plan(1));
    });
    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() =>
      expect(result.current.state?.week_start).toBe("2026-08-31"),
    );
    await act(async () => finishSave({ week_start: "2026-08-24", days: plan(1) }));

    expect(result.current.state?.plan[0].meal_id).toBeNull();
    act(() => result.current.setWeek("2026-08-24"));
    await waitFor(() => expect(result.current.state?.plan[0].meal_id).toBe(1));
  });

  it("unassigns a deleted meal from every cached week without refetching", async () => {
    // The server clears the meal from every day of every week, a known
    // effect, so the cached weeks are corrected in place. This used to
    // throw the whole cache away and refetch each week on the next visit.
    const { result } = await renderPlanner();
    mocked.deleteMeal.mockResolvedValue(undefined);

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(mocked.getPlan).toHaveBeenCalledTimes(1));
    await act(() => result.current.deleteMeal(1));

    act(() => result.current.setWeek("2026-08-24"));
    await waitFor(() =>
      expect(result.current.state?.week_start).toBe("2026-08-24"),
    );
    expect(result.current.state?.plan[0]).toMatchObject({
      meal_id: null,
      servings: null,
    });
    expect(result.current.state?.meals).toHaveLength(0);
    expect(mocked.getPlan).toHaveBeenCalledTimes(1);
  });
});

describe("the grocery list", () => {
  const listFor = (week: string, name: string): GroceryList => ({
    week_start: week,
    lines: [
      {
        key: `${name.toLowerCase()}|g`,
        name,
        qty: 400,
        unit: "g",
        display: "400 g",
        category: null,
        state: null,
        extra_id: null,
      },
    ],
    usuals: [],
    aisle_order: ["produce", "meat", "dairy", "bakery", "pantry", "frozen"],
  });
  const thisWeek = listFor("2026-08-24", "Pasta");
  const nextWeek = listFor("2026-08-31", "Rice");

  beforeEach(() => {
    mocked.getGroceries.mockImplementation(async (week: string) =>
      week === "2026-08-24" ? thisWeek : nextWeek,
    );
  });

  it("loads itself on a page that shows it, and not on any other", async () => {
    const elsewhere = await renderPlanner();
    expect(elsewhere.result.current.grocery).toBeNull();
    expect(mocked.getGroceries).not.toHaveBeenCalled();
    elsewhere.unmount();

    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));
    expect(mocked.getGroceries).toHaveBeenCalledWith("2026-08-24");
  });

  it("belongs to its week, and comes back from memory on returning", async () => {
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    act(() => result.current.setWeek("2026-08-31"));
    await waitFor(() => expect(result.current.grocery).toEqual(nextWeek));

    act(() => result.current.setWeek("2026-08-24"));
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));
    expect(mocked.getGroceries).toHaveBeenCalledTimes(2);
  });

  it("is fetched again after the plan changes, since it is made from the plan", async () => {
    mocked.setPlan.mockImplementation(async (week: string) => ({ week_start: week, days: [] }));
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    await act(() => result.current.savePlan("2026-08-24", []));

    await waitFor(() => expect(mocked.getGroceries).toHaveBeenCalledTimes(2));
  });

  it("reports a list that fails to load", async () => {
    mocked.getGroceries.mockRejectedValue(new ApiError(500, "The list could not be made."));
    const { result } = await renderPlanner({ loadGroceries: true });

    await waitFor(() => expect(result.current.error).toBe("The list could not be made."));
  });

  it("shows a tick at once, then fetches the list again once it is saved", async () => {
    let save!: () => void;
    mocked.setGroceryCheck.mockImplementation(
      () => new Promise<void>((resolve) => (save = resolve)),
    );
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    act(() => void result.current.setGroceryCheck("2026-08-24", "pasta|g", "basket"));

    // Before the server has answered.
    await waitFor(() => expect(result.current.grocery?.lines[0].state).toBe("basket"));
    expect(mocked.getGroceries).toHaveBeenCalledTimes(1);

    await act(async () => save());

    // Then made sure of: whatever else changed on another device shows too.
    await waitFor(() => expect(mocked.getGroceries).toHaveBeenCalledTimes(2));
    expect(mocked.setGroceryCheck).toHaveBeenCalledWith("2026-08-24", "pasta|g", "basket");
  });

  it("puts a tick right, and says so, when it could not be saved", async () => {
    mocked.setGroceryCheck.mockRejectedValue(new ApiError(503, "Couldn't save that tick."));
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    await act(() => result.current.setGroceryCheck("2026-08-24", "pasta|g", "basket"));

    expect(result.current.error).toBe("Couldn't save that tick.");
    // The list is fetched again, and the server's (unticked) version wins.
    await waitFor(() => expect(result.current.grocery?.lines[0].state).toBeNull());
  });

  it("orders the aisles at once, and back again if that fails", async () => {
    mocked.setAisleOrder.mockRejectedValue(new ApiError(503, "Not saved."));
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));
    const before = thisWeek.aisle_order;

    await act(() =>
      result.current.setAisleOrder(["frozen", "pantry", "bakery", "dairy", "meat", "produce"]),
    );

    expect(result.current.grocery?.aisle_order).toEqual(before);
    expect(result.current.error).toBe("Not saved.");
  });

  it("files an added extra under the week the server says, and resolves true", async () => {
    const milk = { ...thisWeek.lines[0], key: "+milk", name: "Milk", extra_id: 4 };
    const withMilk = { ...thisWeek, lines: [...thisWeek.lines, milk] };
    mocked.addExtra.mockResolvedValue(withMilk);
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    let added: boolean | undefined;
    await act(async () => {
      added = await result.current.addExtra("2026-08-24", "milk");
    });

    expect(added).toBe(true);
    expect(result.current.grocery).toEqual(withMilk);
  });

  it("resolves false when an extra is refused, so the field keeps it", async () => {
    mocked.addExtra.mockRejectedValue(new ApiError(422, "Say what to add, like 2 L milk."));
    const { result } = await renderPlanner({ loadGroceries: true });
    await waitFor(() => expect(result.current.grocery).toEqual(thisWeek));

    let added: boolean | undefined;
    await act(async () => {
      added = await result.current.addExtra("2026-08-24", "2 kg");
    });

    expect(added).toBe(false);
    expect(result.current.error).toBe("Say what to add, like 2 L milk.");
  });
});

describe("the week in the URL", () => {
  it("opens the week named in the link", async () => {
    window.history.replaceState(null, "", "/?week=2026-08-31");

    const { result } = await renderPlanner();

    expect(result.current.week).toBe("2026-08-31");
    expect(mocked.getState).toHaveBeenCalledWith("2026-08-31");
  });

  it("snaps any day in the link to its Monday", async () => {
    window.history.replaceState(null, "", "/?week=2026-09-03");

    const { result } = await renderPlanner();

    expect(result.current.week).toBe("2026-08-31");
  });

  it.each(["not-a-date", "2026-13-45", ""])(
    "falls back to this week for %j",
    async (raw) => {
      window.history.replaceState(null, "", `/?week=${raw}`);

      const { result } = await renderPlanner();

      expect(result.current.week).toBe("2026-08-24");
    },
  );

  it("writes the week back to the URL without adding history", async () => {
    const { result } = await renderPlanner();
    const historyLength = window.history.length;

    act(() => result.current.setWeek("2026-08-31"));

    expect(new URLSearchParams(window.location.search).get("week")).toBe(
      "2026-08-31",
    );
    expect(window.history.length).toBe(historyLength);
  });
});

describe("pending work and errors", () => {
  it("tracks pending work per area, not globally", async () => {
    const { result } = await renderPlanner();
    let finishSave!: (plan: { week_start: string; days: [] }) => void;
    mocked.setPlan.mockReturnValue(
      new Promise((resolve) => {
        finishSave = resolve;
      }),
    );

    act(() => {
      void result.current.savePlan("2026-08-24", []);
    });
    await waitFor(() => expect(result.current.planPending).toBe(true));
    // Saving the plan must not freeze meal editing.
    expect(result.current.mealsPending).toBe(false);

    await act(async () => finishSave({ week_start: "2026-08-24", days: [] }));
    await waitFor(() => expect(result.current.planPending).toBe(false));
  });

  it("reports a failed action, and clears it on dismiss", async () => {
    const { result } = await renderPlanner();
    mocked.deleteMeal.mockRejectedValue(new ApiError(404, "No meal with id 1."));

    await act(() => result.current.deleteMeal(1));
    expect(result.current.error).toBe("No meal with id 1.");

    act(() => result.current.dismissError());
    expect(result.current.error).toBeNull();
  });

  it("reports a failed first load", async () => {
    mocked.getState.mockRejectedValue(new ApiError(503, "Database unavailable."));
    const client = createQueryClient({ retry: false });
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children);

    const { result } = renderHook(() => usePlanner(), { wrapper });

    await waitFor(() => expect(result.current.error).toBe("Database unavailable."));
    expect(result.current.state).toBeNull();
  });
});

describe("trying a failed load again", () => {
  it("fetches again what failed, and loads", async () => {
    mocked.getState.mockRejectedValueOnce(new ApiError(503, "Database unavailable."));
    const client = createQueryClient({ retry: false });
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children);
    const { result } = renderHook(() => usePlanner(), { wrapper });
    await waitFor(() => expect(result.current.loadFailed).toBe(true));

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.state).not.toBeNull());
    expect(result.current.loadFailed).toBe(false);
    expect(result.current.error).toBeNull();
  });
});

describe("opening on the last visit's data", () => {
  const WEEK = "2026-08-24";
  const kept = makeState({
    week_start: WEEK,
    meals: [makeMeal({ id: 1, name: "Spaghetti (last visit)" })],
    plan: plan(1),
  });
  const keptList: GroceryList = {
    week_start: WEEK,
    lines: [],
    usuals: [],
    aisle_order: ["produce", "meat", "dairy", "bakery", "pantry", "frozen"],
  };

  beforeEach(() => {
    localStorage.clear();
    saveLastVisit({ state: kept, groceries: [keptList] });
  });

  afterEach(() => {
    clearLastVisit();
    localStorage.clear();
  });

  /** Start as the app does: the kept copy restored before the first render. */
  function renderRestored(options: Parameters<typeof usePlanner>[0] = {}) {
    const client = createQueryClient({ retry: false });
    restoreLastVisit(client);
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children);
    return renderHook(() => usePlanner(options), { wrapper });
  }

  /** A response that arrives when the test says. */
  function held<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((r) => (resolve = r));
    return { promise, resolve };
  }

  it("shows it straight away, as updating, while one request fetches the real thing", async () => {
    const answer = held<ReturnType<typeof makeState>>();
    mocked.getState.mockReturnValue(answer.promise);

    const { result } = renderRestored();

    expect(result.current.state?.meals[0].name).toBe("Spaghetti (last visit)");
    expect(result.current.freshness).toBe("updating");

    await act(async () =>
      answer.resolve(makeState({ week_start: WEEK, meals: [makeMeal({ id: 1 })], plan: plan(1) })),
    );

    await waitFor(() => expect(result.current.freshness).toBe("live"));
    expect(result.current.state?.meals[0].name).toBe("Spaghetti");
    // The plan came with the state, as on any first load.
    expect(mocked.getState).toHaveBeenCalledTimes(1);
    expect(mocked.getPlan).not.toHaveBeenCalled();
  });

  it("keeps showing it, as offline, when the real thing cannot be fetched", async () => {
    mocked.getState.mockRejectedValueOnce(
      new ApiError(0, "Couldn't reach the server. Check your connection and try again."),
    );

    const { result } = renderRestored();

    await waitFor(() => expect(result.current.freshness).toBe("offline"));
    expect(result.current.state?.meals[0].name).toBe("Spaghetti (last visit)");
    expect(result.current.loadFailed).toBe(true);

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.freshness).toBe("live"));
    expect(result.current.state?.meals[0].name).toBe("Spaghetti");
  });

  it("waits for the grocery list too, on a page that shows it", async () => {
    const list = held<GroceryList>();
    mocked.getGroceries.mockReturnValue(list.promise);

    const { result } = renderRestored({ loadGroceries: true });

    expect(result.current.grocery).toEqual(keptList);
    await waitFor(() => expect(mocked.getState).toHaveBeenCalled());
    // The meals and plan are current; the list on screen is not, yet.
    await waitFor(() =>
      expect(result.current.state?.meals[0].name).toBe("Spaghetti"),
    );
    expect(result.current.freshness).toBe("updating");

    await act(async () => list.resolve({ ...keptList, usuals: [] }));
    await waitFor(() => expect(result.current.freshness).toBe("live"));
  });

  it("is live from the start when nothing was kept", async () => {
    localStorage.clear();

    const { result } = renderRestored();
    await waitFor(() => expect(result.current.state).not.toBeNull());

    expect(result.current.freshness).toBe("live");
  });
});
