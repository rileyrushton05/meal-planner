import type { Breadcrumb, ErrorEvent } from "@sentry/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const sentry = vi.hoisted(() => ({
  init: vi.fn(),
  setTag: vi.fn(),
  addBreadcrumb: vi.fn(),
  captureException: vi.fn(() => "7fd59a6813dc435ab5f1079cbe609687"),
}));
vi.mock("./sentry", () => sentry);

import {
  EMAIL_PLACEHOLDER,
  ENVELOPE_PATH,
  initErrorTracking,
  noteApiFailure,
  reportCrash,
  scrubBreadcrumb,
  scrubEvent,
} from "./monitoring";

type Integration = { name: string };

afterEach(() => vi.clearAllMocks());

const CONFIG = {
  dsn: "https://publickey@o1.ingest.de.sentry.io/42",
  environment: "production",
  release: "abc123",
};

describe("starting", () => {
  it("does nothing without a DSN, so development and tests send nothing", async () => {
    const load = vi.fn();

    expect(await initErrorTracking({ ...CONFIG, dsn: "" }, load)).toBe(false);
    // Not even loaded: the page carries none of it.
    expect(load).not.toHaveBeenCalled();
    expect(reportCrash(new Error("x"))).toBeUndefined();
  });

  it("sends through the app's own API, with personal data turned off", async () => {
    expect(await initErrorTracking(CONFIG)).toBe(true);

    const options = sentry.init.mock.calls[0][0];
    expect(options.tunnel).toBe(ENVELOPE_PATH);
    expect(options.dataCollection).toEqual({
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    });
    expect(sentry.setTag).toHaveBeenCalledWith("side", "web");
  });

  it("leaves out session tracking, which would send a request on every page load", async () => {
    await initErrorTracking(CONFIG);

    const defaults = ["BrowserSession", "GlobalHandlers", "Breadcrumbs"].map(
      (name) => ({ name }) as Integration,
    );
    const kept = sentry.init.mock.calls[0][0].integrations(defaults) as Integration[];
    expect(kept.map((integration) => integration.name)).toEqual(["GlobalHandlers", "Breadcrumbs"]);
  });
});

describe("scrubbing", () => {
  it("drops the user and request details, and every email address", () => {
    const event: ErrorEvent = {
      type: undefined,
      user: { email: "cook@example.com", ip_address: "203.0.113.9" },
      request: {
        url: "https://example.app/account?email=cook@example.com",
        headers: { "User-Agent": "x", Referer: "y" },
        cookies: { "__Host-session": "token" },
      },
      exception: { values: [{ type: "Error", value: "No account for Cook.Two+x@mail.example.org" }] },
    };

    const scrubbed = scrubEvent(event);

    expect(scrubbed.user).toBeUndefined();
    expect(scrubbed.request).toEqual({ url: "https://example.app/account" });
    expect(scrubbed.exception?.values?.[0].value).toBe(`No account for ${EMAIL_PLACEHOLDER}`);
    expect(JSON.stringify(scrubbed)).not.toContain("@");
  });

  it("drops console output, and scrubs every other trail entry", () => {
    expect(scrubBreadcrumb({ category: "console", message: "anything" })).toBeNull();
    expect(scrubBreadcrumb({ category: "ui.click", message: "typed cook@example.com" } as Breadcrumb)).toEqual({
      category: "ui.click",
      message: `typed ${EMAIL_PLACEHOLDER}`,
    });
  });
});

it("reports a caught crash and hands back its reference", async () => {
  await initErrorTracking(CONFIG);

  expect(reportCrash(new Error("render failed"), "in App")).toBe("7fd59a6813dc435ab5f1079cbe609687");
  expect(sentry.captureException).toHaveBeenCalledWith(expect.any(Error), {
    contexts: { react: { componentStack: "in App" } },
  });
});

it("notes an API failure with the request id that finds its server logs", async () => {
  await initErrorTracking(CONFIG);
  noteApiFailure("POST", "/api/meals?x=1", 500, "4f9c1d2e-1111-2222-3333-444455556666");

  expect(sentry.addBreadcrumb).toHaveBeenCalledWith({
    category: "api",
    level: "error",
    message: "POST /api/meals 500",
    data: { request_id: "4f9c1d2e-1111-2222-3333-444455556666" },
  });
});
