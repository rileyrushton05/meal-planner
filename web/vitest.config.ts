import { configDefaults, defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      // Playwright's specs run in a real browser, not here.
      exclude: [...configDefaults.exclude, "e2e/**", "screenshots/**"],
      css: false,
      coverage: {
        provider: "v8",
        include: ["src/**"],
        // shadcn primitives are vendored, and main.tsx only mounts the app.
        exclude: ["src/components/ui/**", "src/test/**", "src/main.tsx", "**/*.test.*"],
        reporter: ["text-summary", "text"],
        // Just under what was measured, so coverage cannot fall silently.
        // Raise these as tests are added; never lower them to pass a build.
        thresholds: { statements: 79, branches: 81, functions: 70, lines: 81 },
      },
    },
  }),
);
