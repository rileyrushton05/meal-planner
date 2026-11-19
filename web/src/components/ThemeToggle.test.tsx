import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { ThemeToggle } from "@/components/ThemeToggle";
import { useTheme } from "@/hooks/useTheme";
import { THEME_STORAGE_KEY } from "@/lib/theme";

function Harness() {
  const { theme, setTheme } = useTheme();
  return <ThemeToggle theme={theme} onChange={setTheme} />;
}

const isDarkNow = () => document.documentElement.classList.contains("dark");
const toggle = () => screen.getByRole("button", { name: "Dark theme" });

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

it("starts dark, with the toggle pressed", () => {
  render(<Harness />);
  expect(isDarkNow()).toBe(true);
  expect(toggle()).toHaveAttribute("aria-pressed", "true");
  expect(toggle()).toHaveAttribute("title", "Switch to light theme");
});

it("switches to light and remembers it, and back again", async () => {
  const user = userEvent.setup();
  render(<Harness />);

  await user.click(toggle());

  expect(isDarkNow()).toBe(false);
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  expect(toggle()).toHaveAttribute("aria-pressed", "false");
  expect(toggle()).toHaveAttribute("title", "Switch to dark theme");

  await user.click(toggle());

  expect(isDarkNow()).toBe(true);
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
});
