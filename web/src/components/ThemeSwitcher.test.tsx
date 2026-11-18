import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useTheme } from "@/hooks/useTheme";
import { THEME_STORAGE_KEY } from "@/lib/theme";

function Harness() {
  const { theme, setTheme } = useTheme();
  return <ThemeSwitcher theme={theme} onChange={setTheme} />;
}

const isDarkNow = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

it("starts dark, with Dark pressed", () => {
  render(<Harness />);
  expect(isDarkNow()).toBe(true);
  expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("switches to light and remembers it", async () => {
  const user = userEvent.setup();
  render(<Harness />);

  await user.click(screen.getByRole("button", { name: "Light theme" }));

  expect(isDarkNow()).toBe(false);
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  expect(screen.getByRole("button", { name: "Light theme" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

it("offers only light and dark", () => {
  render(<Harness />);
  expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
    "Light theme",
    "Dark theme",
  ]);
});
