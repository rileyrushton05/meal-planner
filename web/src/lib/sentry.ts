/**
 * The only parts of the Sentry SDK the page uses, loaded on demand by
 * src/lib/monitoring.ts. Importing them by name lets the bundler leave out
 * the rest of the SDK (session replay, the feedback widget...), which a
 * dynamic import of the whole package would pull in.
 */
export { addBreadcrumb, captureException, init, setTag } from "@sentry/react";
