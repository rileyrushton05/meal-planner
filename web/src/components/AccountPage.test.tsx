import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import type { Account, AccountExport } from "@/api/types";
import { AccountPage } from "@/components/AccountPage";

const ACCOUNT: Account = { email: "cook@example.com", is_guest: false, has_recovery_code: true };
const GUEST: Account = { email: null, is_guest: true, has_recovery_code: false };
const EXPORT: AccountExport = {
  format: "meal-planner-export",
  version: 1,
  exported_at: "2026-11-18T09:00:00Z",
  account: { email: "cook@example.com", is_guest: false, created_at: null },
  meals: [{ name: "Tacos", servings: 4, ingredients: [] }],
  plans: [],
};

afterEach(() => vi.restoreAllMocks());

function renderPage(account: Account = ACCOUNT, overrides: Partial<Parameters<typeof AccountPage>[0]> = {}) {
  const props = {
    account,
    onReplaceRecoveryCode: vi.fn(async (_password: string) => "NEW0-CODE-1234-5678"),
    onExport: vi.fn(async () => EXPORT),
    onDelete: vi.fn(async (_password?: string) => {}),
    ...overrides,
  };
  return { ...render(<AccountPage {...props} />), props };
}

const dialog = () => screen.getByRole("alertdialog");

describe("who", () => {
  it("names the account, or explains a guest session", () => {
    const { unmount } = renderPage();
    expect(screen.getByRole("region", { name: "Your account" })).toHaveTextContent(
      "cook@example.com",
    );
    unmount();

    renderPage(GUEST);
    expect(screen.getByRole("region", { name: "Guest session" })).toHaveTextContent(
      /until you sign up/,
    );
  });
});

describe("downloading your data", () => {
  it("saves everything as a dated JSON file", async () => {
    const user = userEvent.setup();
    const created: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      created.push(blob as Blob);
      return "blob:export";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { props } = renderPage();

    await user.click(screen.getByRole("button", { name: "Download my data" }));

    expect(props.onExport).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toMatch(/^the-fridge-door-export-\d{4}-\d{2}-\d{2}\.json$/);
    expect(JSON.parse(await created[0].text())).toEqual(EXPORT);
  });

  it("says so when it fails", async () => {
    const user = userEvent.setup();
    renderPage(ACCOUNT, {
      onExport: vi.fn(async () => {
        throw new ApiError(503, "Database unavailable.");
      }),
    });

    await user.click(screen.getByRole("button", { name: "Download my data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable.");
  });
});

describe("deleting", () => {
  it("asks an account for its password, and sends it", async () => {
    const user = userEvent.setup();
    const { props } = renderPage();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    const confirm = within(dialog()).getByRole("button", { name: "Delete for good" });
    // Nothing to send yet.
    expect(confirm).toBeDisabled();
    expect(within(dialog()).getByLabelText("Password")).toHaveFocus();

    await user.keyboard("lettuce harbour spoon{Enter}");

    expect(props.onDelete).toHaveBeenCalledWith("lettuce harbour spoon");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("keeps the dialog open with the reason when the password is wrong", async () => {
    const user = userEvent.setup();
    renderPage(ACCOUNT, {
      onDelete: vi.fn(async () => {
        throw new ApiError(401, "That password isn't right.");
      }),
    });

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await user.type(within(dialog()).getByLabelText("Password"), "guess{Enter}");

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(
      "That password isn't right.",
    );
    expect(within(dialog()).getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });

  it("asks a guest for nothing but a second thought", async () => {
    const user = userEvent.setup();
    const { props } = renderPage(GUEST);

    await user.click(screen.getByRole("button", { name: "Delete everything" }));
    expect(within(dialog()).queryByLabelText("Password")).not.toBeInTheDocument();
    await user.click(within(dialog()).getByRole("button", { name: "Delete for good" }));

    expect(props.onDelete).toHaveBeenCalledWith(undefined);
  });

  it("does nothing when cancelled, and forgets what was typed", async () => {
    const user = userEvent.setup();
    const { props } = renderPage();

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await user.type(within(dialog()).getByLabelText("Password"), "half typed");
    await user.click(within(dialog()).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Delete account" }));
    expect(within(dialog()).getByLabelText("Password")).toHaveValue("");
    expect(props.onDelete).not.toHaveBeenCalled();
  });
});

describe("the recovery code", () => {
  it("warns an account that has none, and makes one with the password", async () => {
    const user = userEvent.setup();
    const { props } = renderPage({ ...ACCOUNT, has_recovery_code: false });

    const section = screen.getByRole("region", { name: "Recovery code" });
    expect(section).toHaveTextContent("You don't have a recovery code yet");
    await user.click(within(section).getByRole("button", { name: "Make a recovery code" }));
    await user.type(within(dialog()).getByLabelText("Password"), "lettuce harbour spoon{Enter}");

    expect(props.onReplaceRecoveryCode).toHaveBeenCalledWith("lettuce harbour spoon");
    const saveCode = await screen.findByRole("alertdialog", { name: "Save your recovery code" });
    expect(saveCode).toHaveTextContent("NEW0-CODE-1234-5678");
  });

  it("offers a replacement to an account that has one", () => {
    renderPage();

    const section = screen.getByRole("region", { name: "Recovery code" });
    expect(section).not.toHaveTextContent("You don't have");
    expect(
      within(section).getByRole("button", { name: "Make a new recovery code" }),
    ).toBeInTheDocument();
  });

  it("is not offered to a guest, who has no password to recover", () => {
    renderPage(GUEST);

    expect(screen.queryByRole("region", { name: "Recovery code" })).not.toBeInTheDocument();
  });
});
