import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { ApiError, api } from "@/api/client";
import { createQueryClient } from "@/api/queryClient";
import { makeMeal, makeState } from "@/test/factories";

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  api: {
    getState: vi.fn(),
    getPlan: vi.fn(),
    getGroceryList: vi.fn(),
    me: vi.fn(),
    signUp: vi.fn(),
    logIn: vi.fn(),
    logOut: vi.fn(),
    deleteAccount: vi.fn(),
    exportAccount: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
  mocked.getState.mockImplementation(async (week: string) =>
    makeState({ week_start: week, meals: [makeMeal({ id: 1, name: "Spaghetti" })] }),
  );
  mocked.me.mockResolvedValue({ email: null, is_guest: true });
  mocked.getGroceryList.mockResolvedValue([]);
});

async function renderApp(path = "/") {
  window.history.replaceState(null, "", path);
  render(
    <QueryClientProvider client={createQueryClient({ retry: false })}>
      <App />
    </QueryClientProvider>,
  );
  // Wait for the first load, so assertions see the loaded app.
  await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
}

const heading = () => screen.getByRole("heading", { level: 1 });
const currentLink = () =>
  within(screen.getByRole("navigation", { name: "Pages" }))
    .getAllByRole("link")
    .find((link) => link.getAttribute("aria-current") === "page");

describe("pages", () => {
  it("opens on this week", async () => {
    await renderApp();

    expect(heading()).toHaveTextContent("This week");
    expect(currentLink()).toHaveTextContent("This week");
    expect(document.title).toBe("This week · Meal Planner");
  });

  it("names home for the week it shows", async () => {
    const user = userEvent.setup();
    await renderApp();

    await user.click(screen.getByRole("button", { name: "Next week" }));
    expect(heading()).toHaveTextContent("Next week");
    expect(document.title).toBe("Next week · Meal Planner");
    // Other pages keep their own names in any week.
    await user.click(screen.getByRole("link", { name: "Plan" }));
    expect(heading()).toHaveTextContent("Weekly plan");
  });

  it("loads the grocery list only on the pages that show it", async () => {
    const user = userEvent.setup();
    await renderApp("/meals");
    await user.click(screen.getByRole("link", { name: "Plan" }));
    expect(mocked.getGroceryList).not.toHaveBeenCalled();

    await user.click(screen.getByRole("link", { name: "Groceries" }));
    await waitFor(() => expect(mocked.getGroceryList).toHaveBeenCalledTimes(1));
    // Home's count is the same list, already in memory.
    await user.click(screen.getByRole("link", { name: "This week" }));
    expect(mocked.getGroceryList).toHaveBeenCalledTimes(1);
  });

  it("opens the page in the link", async () => {
    await renderApp("/groceries");

    expect(heading()).toHaveTextContent("Groceries");
    expect(currentLink()).toHaveTextContent("Groceries");
  });

  it("sends a path it does not know home", async () => {
    await renderApp("/settings");

    expect(heading()).toHaveTextContent("This week");
  });

  it("changes page in place, keeping the week, with the back button working", async () => {
    const user = userEvent.setup();
    await renderApp("/plan?week=2026-08-03");

    await user.click(screen.getByRole("link", { name: "Meals" }));

    expect(window.location.pathname).toBe("/meals");
    expect(new URLSearchParams(window.location.search).get("week")).toBe("2026-08-03");
    expect(heading()).toHaveTextContent("Meals");
    // Not a reload: the first load was the only one.
    expect(mocked.getState).toHaveBeenCalledTimes(1);

    window.history.back();
    await waitFor(() => expect(heading()).toHaveTextContent("Weekly plan"));
  });

  it("links carry the week, so one opened in a new tab shows it too", async () => {
    await renderApp("/plan?week=2026-08-03");

    expect(screen.getByRole("link", { name: "Groceries" })).toHaveAttribute(
      "href",
      "/groceries?week=2026-08-03",
    );
  });

  it("shows the week picker only where the week matters", async () => {
    await renderApp("/meals");
    expect(screen.queryByLabelText("Week starting")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("link", { name: "Groceries" }));
    expect(screen.getByLabelText("Week starting")).toBeInTheDocument();
  });
});

describe("loading", () => {
  it("shows the week from the link once loaded", async () => {
    await renderApp("/?week=2026-08-05");

    expect(mocked.getState).toHaveBeenCalledWith("2026-08-03");
    expect(screen.getByLabelText("Week starting")).toHaveValue("2026-08-03");
  });
});

describe("the account", () => {
  it("invites a guest to sign up, and keeps their meals when they do", async () => {
    const user = userEvent.setup();
    mocked.signUp.mockResolvedValue({ email: "cook@example.com", is_guest: false });
    await renderApp("/meals");

    await user.click(await screen.findByRole("button", { name: "Sign up to keep your meals" }));
    const dialog = screen.getByRole("dialog", { name: "Create an account" });
    await user.type(within(dialog).getByLabelText("Email"), "cook@example.com");
    await user.type(within(dialog).getByLabelText("Password"), "lettuce harbour spoon");
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));

    expect(mocked.signUp).toHaveBeenCalledWith("cook@example.com", "lettuce harbour spoon");
    expect(await screen.findByText("cook@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Same account, same meals: nothing is refetched.
    expect(mocked.getState).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("article", { name: "Spaghetti" })).toBeInTheDocument();
  });

  it("shows the server's reason when signing up fails, and stays open", async () => {
    const user = userEvent.setup();
    mocked.signUp.mockRejectedValue(
      new ApiError(422, "That password is one of the most common."),
    );
    await renderApp();

    await user.click(await screen.findByRole("button", { name: "Sign up to keep your meals" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Email"), "cook@example.com");
    await user.type(within(dialog).getByLabelText("Password"), "password1");
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "That password is one of the most common.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("loads the account's own meals after logging in", async () => {
    const user = userEvent.setup();
    mocked.logIn.mockImplementation(async () => {
      const account = { email: "cook@example.com", is_guest: false };
      mocked.me.mockResolvedValue(account);
      mocked.getState.mockImplementation(async (week: string) =>
        makeState({ week_start: week, meals: [makeMeal({ id: 9, name: "Their Curry" })] }),
      );
      return account;
    });
    await renderApp("/meals");

    await user.click(await screen.findByRole("button", { name: "Log in" }));
    const dialog = screen.getByRole("dialog", { name: "Log in" });
    await user.type(within(dialog).getByLabelText("Email"), "cook@example.com");
    await user.type(within(dialog).getByLabelText("Password"), "lettuce harbour spoon");
    await user.click(within(dialog).getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("article", { name: "Their Curry" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Spaghetti" })).not.toBeInTheDocument();
    expect(await screen.findByText("cook@example.com")).toBeInTheDocument();
  });

  it("starts over as a guest after logging out", async () => {
    const user = userEvent.setup();
    mocked.me.mockResolvedValue({ email: "cook@example.com", is_guest: false });
    mocked.logOut.mockImplementation(async () => {
      mocked.me.mockResolvedValue({ email: null, is_guest: true });
    });
    await renderApp();

    await user.click(await screen.findByRole("button", { name: "Log out" }));

    expect(
      await screen.findByRole("button", { name: "Sign up to keep your meals" }),
    ).toBeInTheDocument();
    expect(mocked.getState).toHaveBeenCalledTimes(2);
  });
});

describe("the account page", () => {
  it("is reached from the account controls, not the main navigation", async () => {
    const user = userEvent.setup();
    await renderApp("/meals");

    const nav = screen.getByRole("navigation", { name: "Pages" });
    expect(within(nav).queryByRole("link", { name: "Account" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Account" }));
    expect(heading()).toHaveTextContent("Account");
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
  });

  it("after deleting, lands home in a fresh session with nothing of the old account", async () => {
    const user = userEvent.setup();
    mocked.me.mockResolvedValue({ email: "cook@example.com", is_guest: false });
    mocked.deleteAccount.mockImplementation(async () => {
      mocked.me.mockResolvedValue({ email: null, is_guest: true });
      mocked.getState.mockImplementation(async (week: string) =>
        makeState({ week_start: week, meals: [] }),
      );
    });
    await renderApp("/account");

    await user.click(await screen.findByRole("button", { name: "Delete account" }));
    await user.type(screen.getByLabelText("Password"), "lettuce harbour spoon{Enter}");

    expect(mocked.deleteAccount).toHaveBeenCalledWith("lettuce harbour spoon");
    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByText(/everything in it have been deleted/)).toBeInTheDocument();
    await waitFor(() => expect(mocked.getState).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByRole("button", { name: "Sign up to keep your meals" }),
    ).toBeInTheDocument();
  });
});
