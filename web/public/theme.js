/*
 * Puts the saved theme on <html> before the page first paints, so it never
 * flashes dark-then-light. The app takes over from here (src/lib/theme.ts,
 * which applies the same rules and must stay in step with this).
 *
 * A file rather than an inline script so a Content-Security-Policy can allow
 * it as 'self', without 'unsafe-inline'. A classic script, not a module, so it runs
 * synchronously in <head>, before anything is drawn.
 */
(function () {
  var dark = true;
  try {
    dark = localStorage.getItem("theme") !== "light";
  } catch {
    // Storage blocked (some private modes): the default it is.
  }
  document.documentElement.classList.toggle("dark", dark);
})();
