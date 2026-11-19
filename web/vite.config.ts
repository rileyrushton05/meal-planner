import { readFileSync } from "node:fs";

import { sentryVitePlugin } from "@sentry/vite-plugin";
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

/**
 * Error tracking (src/lib/monitoring.ts), from the deployment's environment.
 *
 * Only these three values are built into the page, each named here. The
 * environment also holds SENTRY_AUTH_TOKEN, a real secret, which is why
 * this does not widen Vite's `envPrefix` to let SENTRY_* through.
 */
const errorTracking = {
  "import.meta.env.VITE_SENTRY_DSN": JSON.stringify(process.env.SENTRY_DSN ?? ""),
  "import.meta.env.VITE_SENTRY_ENVIRONMENT": JSON.stringify(process.env.VERCEL_ENV ?? "development"),
  "import.meta.env.VITE_SENTRY_RELEASE": JSON.stringify(process.env.VERCEL_GIT_COMMIT_SHA ?? ""),
};

/**
 * With an auth token (deployments only), upload source maps so a report
 * from the minified page shows the real file and line, then delete them:
 * they are for Sentry, not for anyone browsing the site. A failed upload
 * warns rather than failing the deploy.
 */
const uploadSourceMaps = Boolean(process.env.SENTRY_AUTH_TOKEN);
const sourceMapPlugins = uploadSourceMaps
  ? [
      sentryVitePlugin({
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        release: { name: process.env.VERCEL_GIT_COMMIT_SHA },
        sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
        telemetry: false,
        errorHandler: (error) => console.warn("Sentry source map upload failed:", error.message),
      }),
    ]
  : [];

export default defineConfig({
  plugins: [react(), tailwindcss(), ...sourceMapPlugins],
  define: errorTracking,
  build: {
    // "hidden": maps are written for the upload, but the page never points
    // at them.
    sourcemap: uploadSourceMaps ? "hidden" : false,
  },
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
