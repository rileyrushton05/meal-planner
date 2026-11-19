/// <reference types="vite/client" />

// Built in by vite.config.ts from the deployment's environment. All three
// are empty outside a deployment, which turns error tracking off.
interface ImportMetaEnv {
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_SENTRY_ENVIRONMENT?: string;
  readonly VITE_SENTRY_RELEASE?: string;
}
