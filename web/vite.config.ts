import { readFileSync } from "node:fs";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * The web page's security headers, read from vercel.json, where production
 * gets them. `vite preview` serves the production build with the same
 * headers, so the end-to-end tests run under the real Content-Security-
 * Policy and fail on anything it would block. One copy, so the two cannot
 * drift apart. Not applied to the dev server, whose hot reloading relies on
 * inline scripts the policy rightly forbids.
 */
function pageHeaders(): Record<string, string> {
  const config = JSON.parse(readFileSync(new URL("../vercel.json", import.meta.url), "utf8")) as {
    headers?: { source: string; headers: { key: string; value: string }[] }[];
  };
  const rule = config.headers?.find((h) => !h.source.startsWith("/api"));
  if (!rule) throw new Error("vercel.json has no headers for the web page.");
  return Object.fromEntries(rule.headers.map(({ key, value }) => [key, value]));
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  server: {
    // In development the API runs separately on :8000. Proxying it under the
    // same origin means no CORS handling and the same relative URLs the
    // production build uses, where Vercel serves both from one domain.
    proxy: {
      // API_PROXY_TARGET lets the end-to-end tests point at their own server
      // instead of the development one. `vite preview` reuses this proxy.
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    headers: pageHeaders(),
  },
});
