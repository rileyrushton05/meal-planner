import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GroceryTab } from "@/components/GroceryTab";

const lines = [
  { name: "Pasta", qty: 400, unit: "g", display: "400 g" },
  { name: "Beef Mince", qty: 1500, unit: "g", display: "1.5 kg" },
];

function renderTab(overrides = {}) {
  const props = {
    weekStart: "2026-08-03",
    lines,
    busy: false,
    onGenerate: vi.fn(),
    ...overrides,
  };
  return { ...render(<GroceryTab {...props} />), props };
}

describe("generating", () => {
  it("prompts before a list exists", () => {
    renderTab({ lines: null });
    expect(screen.getByText(/generate a list/i)).toBeInTheDocument();
  });

  it("says so when the week is empty", () => {
    renderTab({ lines: [] });
    expect(screen.getByText(/no meals assigned/i)).toBeInTheDocument();
  });

  it("asks for a list on request", async () => {
    const user = userEvent.setup();
    const { props } = renderTab({ lines: null });

    await user.click(screen.getByRole("button", { name: /generate list/i }));

    expect(props.onGenerate).toHaveBeenCalled();
  });
});

describe("the list", () => {
  it("shows each line with the amount the API formatted", () => {
    renderTab();
    // 1500 g arrives already scaled to 1.5 kg from the domain layer.
    expect(screen.getByText("1.5 kg")).toBeInTheDocument();
    expect(screen.getByText("400 g")).toBeInTheDocument();
  });

  it("ticks an item off and back on", async () => {
    const user = userEvent.setup();
    renderTab();

    const pasta = screen.getByRole("button", { name: /Pasta/ });
    expect(pasta).toHaveAttribute("aria-pressed", "false");

    await user.click(pasta);
    expect(pasta).toHaveAttribute("aria-pressed", "true");

    await user.click(pasta);
    expect(pasta).toHaveAttribute("aria-pressed", "false");
  });

  it("counts what is in the basket", async () => {
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: /Pasta/ }));

    expect(screen.getByText(/1 in the basket/)).toBeInTheDocument();
  });
});
