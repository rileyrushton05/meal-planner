import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TabPanel, Tabs } from "./Tabs";

const TABS = ["Meals", "Weekly Plan", "Grocery List"] as const;

function renderTabs(active: (typeof TABS)[number] = "Meals") {
  const onChange = vi.fn();
  render(
    <>
      <Tabs tabs={TABS} active={active} onChange={onChange} label="Sections" />
      <TabPanel tab={active}>content</TabPanel>
    </>,
  );
  return { onChange };
}

describe("semantics", () => {
  it("exposes a labelled tablist", () => {
    renderTabs();
    expect(screen.getByRole("tablist", { name: "Sections" })).toBeInTheDocument();
  });

  it("marks only the active tab as selected", () => {
    renderTabs("Weekly Plan");

    expect(screen.getByRole("tab", { selected: true })).toHaveTextContent(
      "Weekly Plan",
    );
    expect(screen.getAllByRole("tab", { selected: false })).toHaveLength(2);
  });

  it("associates the panel with its tab", () => {
    renderTabs("Meals");

    const panel = screen.getByRole("tabpanel");
    const tab = screen.getByRole("tab", { selected: true });
    expect(tab).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", tab.id);
  });
});

describe("keyboard navigation", () => {
  it("keeps a single tab stop, as the ARIA pattern requires", () => {
    renderTabs("Meals");

    const focusable = screen
      .getAllByRole("tab")
      .filter((tab) => tab.getAttribute("tabindex") === "0");
    expect(focusable).toHaveLength(1);
  });

  it("moves to the next tab with the right arrow", async () => {
    const user = userEvent.setup();
    const { onChange } = renderTabs("Meals");

    await user.click(screen.getByRole("tab", { name: "Meals" }));
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenLastCalledWith("Weekly Plan");
  });

  it("wraps from the first tab back to the last with the left arrow", async () => {
    const user = userEvent.setup();
    const { onChange } = renderTabs("Meals");

    await user.click(screen.getByRole("tab", { name: "Meals" }));
    await user.keyboard("{ArrowLeft}");

    expect(onChange).toHaveBeenLastCalledWith("Grocery List");
  });

  it("ignores keys that are not arrows", async () => {
    const user = userEvent.setup();
    const { onChange } = renderTabs("Meals");

    await user.click(screen.getByRole("tab", { name: "Meals" }));
    onChange.mockClear();
    await user.keyboard("{ArrowUp}");

    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("pointer navigation", () => {
  it("selects a tab when clicked", async () => {
    const user = userEvent.setup();
    const { onChange } = renderTabs("Meals");

    await user.click(screen.getByRole("tab", { name: "Grocery List" }));

    expect(onChange).toHaveBeenCalledWith("Grocery List");
  });
});
