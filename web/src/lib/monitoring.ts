import type { Breadcrumb, ErrorEvent } from "@sentry/react";

/**
 * Error tracking for the page: crashes are reported to Sentry, through the
 * app's own API (server/routers/monitoring.py) rather than to Sentry
 * directly, so the Content-Security-Policy stays `connect-src 'self'` and
 * ad blockers do not drop the reports.
 *
 * Off unless the build was given a DSN (vite.config.ts), so development,
 * tests and forks send nothing. What a report may contain is decided here:
 * no user, cookies, headers, bodies or query strings; console output is not
 * kept; and anything shaped like an email address is replaced wherever it
 * appears. The server applies the same rules to its own reports.
 *
 * The SDK is loaded on its own, after the app has started, so the first
 * paint never waits on it (it is about a fifth of the page's JavaScript).
 * The cost: a crash in the moment before it arrives still shows the crash
 * screen, but is not reported.
 */

type SentryModule = typeof import("./sentry");

/** The loaded SDK, once tracking has started; null while it is off. */
let sentry: SentryModule | null = null;

export const ENVELOPE_PATH = "/api/monitoring/envelope";
export const EMAIL_PLACEHOLDER = "[email]";

const EMAIL = /[^\s@<>()[\]{}"',;:]+@[^\s@<>()[\]{}"',;:]+\.[A-Za-z]{2,}/g;

export interface ErrorTrackingConfig {
  dsn: string;
  environment: string;
  release: string;
}

const BUILT_IN: ErrorTrackingConfig = {
  dsn: import.meta.env.VITE_SENTRY_DSN ?? "",
  environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? "development",
  release: import.meta.env.VITE_SENTRY_RELEASE ?? "",
};

/** Start reporting if a DSN was built in. Resolves to whether it did. */
export async function initErrorTracking(
  config: ErrorTrackingConfig = BUILT_IN,
  load: () => Promise<SentryModule> = () => import("./sentry"),
): Promise<boolean> {
  if (!config.dsn) return false;
  const Sentry = await load();
  Sentry.init({
    dsn: config.dsn,
    tunnel: ENVELOPE_PATH,
    environment: config.environment,
    release: config.release || undefined,
    // Every kind of personal data the SDK could attach, turned off by name.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    },
    // Session tracking would send a request on every page load; only
    // errors are wanted.
    integrations: (defaults) => defaults.filter((integration) => integration.name !== "BrowserSession"),
    beforeSend: scrubEvent,
    beforeBreadcrumb: scrubBreadcrumb,
  });
  Sentry.setTag("side", "web");
  sentry = Sentry;
  return true;
}

/**
 * Report a crash the page caught. Returns the report's id, to show the
 * person as a reference, or undefined when tracking is off.
 */
export function reportCrash(error: unknown, componentStack?: string): string | undefined {
  return sentry?.captureException(error, {
    contexts: componentStack ? { react: { componentStack } } : undefined,
  });
}

/** Remove personal data from a report before it is sent. */
export function scrubEvent(event: ErrorEvent): ErrorEvent {
  delete event.user;
  if (event.request) {
    event.request = { url: event.request.url?.split("?")[0] };
  }
  return withoutEmails(event);
}

/** Console output can hold anything, so it is not kept; the rest is scrubbed. */
export function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb | null {
  if (crumb.category === "console") return null;
  return withoutEmails(crumb);
}

/**
 * Leave a trail entry for an API failure, with the request id that finds
 * the server's log lines for it. If the page then crashes, the report shows
 * which request went wrong first. Does nothing while tracking is off.
 */
export function noteApiFailure(method: string, path: string, status: number, requestId: string | null) {
  sentry?.addBreadcrumb({
    category: "api",
    level: status >= 500 ? "error" : "warning",
    message: `${method} ${path.split("?")[0]} ${status}`,
    data: requestId ? { request_id: requestId } : undefined,
  });
}

export function withoutEmails<T>(value: T): T {
  if (typeof value === "string") return value.replace(EMAIL, EMAIL_PLACEHOLDER) as T;
  if (Array.isArray(value)) return value.map((item) => withoutEmails(item)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, withoutEmails(item)]),
    ) as T;
  }
  return value;
}
