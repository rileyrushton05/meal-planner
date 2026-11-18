/**
 * Light or dark. Dark by default.
 *
 * The choice is a per-browser convenience, so it lives in localStorage, not
 * on the account. public/theme.js applies it before first paint; these are
 * the same rules for the running app, and the two must stay in step.
 */

export const THEMES = ["light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = "dark";
export const THEME_STORAGE_KEY = "theme";

export function isTheme(value: unknown): value is Theme {
  return THEMES.includes(value as Theme);
}

/**
 * The saved choice, or the default if there is none, it is one this app no
 * longer offers (such as "system"), or storage is blocked.
 */
export function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(saved) ? saved : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage blocked: the choice lasts until the page closes.
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}
