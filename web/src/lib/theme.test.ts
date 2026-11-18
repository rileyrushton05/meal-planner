import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The script exactly as the page loads it, as text, to run here.
import prePaintScript from "../../public/theme.js?raw";

import { applyTheme, savedTheme, saveTheme, THEME_STORAGE_KEY } from "./theme";

const isDarkNow = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the saved choice", () => {
  it("is dark until something else is chosen", () => {
    expect(savedTheme()).toBe("dark");
    saveTheme("light");
    expect(savedTheme()).toBe("light");
  });

  it("ignores a value it does not recognise", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "synthwave");
    expect(savedTheme()).toBe("dark");
  });

  it("falls back to the default when storage is blocked", () => {
    // As in a browser with site data blocked: touching storage throws.
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
    });
    expect(savedTheme()).toBe("dark");
    expect(() => saveTheme("light")).not.toThrow();
  });
});

// The pre-paint script and the app must agree, or the page would flip on
// load. Both are run over the same cases.
describe.each([
  [
    "the app",
    (theme: string | null) => {
      if (theme) localStorage.setItem(THEME_STORAGE_KEY, theme);
      applyTheme(savedTheme());
    },
  ],
  [
    "the pre-paint script",
    (theme: string | null) => {
      if (theme) localStorage.setItem(THEME_STORAGE_KEY, theme);
      new Function(prePaintScript)();
    },
  ],
])("%s", (_name, apply) => {
  it.each([
    [null, true],
    ["dark", true],
    ["light", false],
    // Saved back when there was a "match the device" option.
    ["system", true],
  ] as const)("shows %s as dark=%s", (theme, dark) => {
    apply(theme);
    expect(isDarkNow()).toBe(dark);
  });
});

it("the pre-paint script falls back to dark when storage is blocked", () => {
  vi.stubGlobal("localStorage", {
    getItem: () => {
      throw new DOMException("blocked", "SecurityError");
    },
  });
  expect(() => new Function(prePaintScript)()).not.toThrow();
  expect(isDarkNow()).toBe(true);
});
