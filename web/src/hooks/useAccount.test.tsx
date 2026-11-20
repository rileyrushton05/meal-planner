import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { STORAGE_KEY, clearLastVisit, keepLastVisit } from "@/api/persistence";
import { createQueryClient, queryKeys } from "@/api/queryClient";
import { SESSION_ENDED_NOTICE, useAccount } from "@/hooks/useAccount";
import { makeState } from "@/test/factories";
import { saveLastVisit } from "@/test/lastVisit";

afterEach(() => vi.unstubAllGlobals());

const respond = (status: number, body: unknown = {}) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
const notSignedIn = respond(401, { type: "urn:meal-planner:problem:not-signed-in" });

function setup() {
  const queryClient = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, ...renderHook(() => useAccount(), { wrapper }) };
}

describe("a session that ends mid-use", () => {
  it("clears what the old session had on screen and says why", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        if (path === "/api/auth/me") return respond(200, { email: "a@b.co", is_guest: false });
        return respond(200);
      }),
    );
    const { queryClient, result } = setup();
    await waitFor(() => expect(result.current.account?.email).toBe("a@b.co"));
    queryClient.setQueryData(queryKeys.library, { meals: [], ingredient_suggestions: [], templates: [] });
    saveLastVisit({ state: makeState() });

    // The session has expired: the next read is refused, the client starts
    // a guest session and retries.
    let guestStarted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        if (path === "/api/auth/guest") {
          guestStarted = true;
          return respond(201);
        }
        if (!guestStarted) return notSignedIn;
        if (path === "/api/auth/me") return respond(200, { email: null, is_guest: true });
        return respond(200, { week_start: "2026-08-03", days: [] });
      }),
    );
    await act(() => api.getPlan("2026-08-03"));

    await waitFor(() => expect(result.current.notice).toBe(SESSION_ENDED_NOTICE));
    expect(queryClient.getQueryData(queryKeys.library)).toBeUndefined();
    // Nor is a copy of it kept for the next visit.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    await waitFor(() => expect(result.current.account?.is_guest).toBe(true));
  });

  it("says nothing on a first visit, when there was nothing to lose", async () => {
    let guestStarted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        if (path === "/api/auth/guest") {
          guestStarted = true;
          return respond(201);
        }
        return guestStarted ? respond(200, { email: null, is_guest: true }) : notSignedIn;
      }),
    );
    const { result } = setup();

    await waitFor(() => expect(result.current.account?.is_guest).toBe(true));
    expect(result.current.notice).toBeNull();
  });
});

describe("a recovery code", () => {
  it("goes to whoever shows it, and is kept nowhere in the app", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        if (path === "/api/auth/me") {
          return respond(200, { email: null, is_guest: true, has_recovery_code: false });
        }
        if (path === "/api/auth/signup") {
          return respond(200, {
            email: "a@b.co",
            is_guest: false,
            has_recovery_code: true,
            recovery_code: "K7QM-3XRD-9PWT-HB2F",
          });
        }
        return respond(200);
      }),
    );
    const { queryClient, result } = setup();
    await waitFor(() => expect(result.current.account?.is_guest).toBe(true));

    let shown = "";
    await act(async () => {
      shown = await result.current.signUp({ email: "a@b.co", password: "lettuce harbour spoon" });
    });

    expect(shown).toBe("K7QM-3XRD-9PWT-HB2F");
    await waitFor(() =>
      expect(result.current.account).toEqual({
        email: "a@b.co",
        is_guest: false,
        has_recovery_code: true,
      }),
    );
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(
      "K7QM",
    );
  });
});

describe("the copy of the last visit kept in the browser", () => {
  const guest = { email: null, is_guest: true, has_recovery_code: false };

  beforeEach(() => {
    localStorage.clear();
    saveLastVisit({ account: guest, state: makeState() });
  });

  afterEach(() => {
    clearLastVisit();
    localStorage.clear();
  });

  function signedInAs(account: object, others: Record<string, ReturnType<typeof respond>> = {}) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path === "/api/auth/me" ? respond(200, account) : (others[path] ?? respond(200)),
      ),
    );
  }

  it.each([
    ["logging out", (r: ReturnType<typeof setup>["result"]) => r.current.logOut()],
    [
      "logging in as someone",
      (r: ReturnType<typeof setup>["result"]) =>
        r.current.logIn({ email: "a@b.co", password: "lettuce harbour spoon" }),
    ],
    ["deleting the account", (r: ReturnType<typeof setup>["result"]) => r.current.deleteAccount()],
  ])("is cleared by %s", async (_, act_) => {
    signedInAs(guest, { "/api/auth/logout": respond(204) });
    const { result } = setup();
    await waitFor(() => expect(result.current.account).not.toBeNull());

    await act(() => act_(result));

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("is kept on signing up: the account and its data are the same", async () => {
    signedInAs(guest, {
      "/api/auth/signup": respond(200, { ...guest, email: "a@b.co", is_guest: false, recovery_code: "K7QM-3XRD" }),
    });
    const { result } = setup();
    await waitFor(() => expect(result.current.account).not.toBeNull());

    await act(() => result.current.signUp({ email: "a@b.co", password: "lettuce harbour spoon" }));

    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull();
  });

  it("never holds a recovery code", async () => {
    signedInAs(guest, {
      "/api/auth/signup": respond(200, { ...guest, email: "a@b.co", is_guest: false, recovery_code: "K7QM-3XRD" }),
    });
    const { queryClient, result } = setup();
    const stop = keepLastVisit(queryClient);
    queryClient.setQueryData(queryKeys.library, { meals: [], ingredient_suggestions: [], templates: [] });
    await waitFor(() => expect(result.current.account).not.toBeNull());

    await act(() => result.current.signUp({ email: "a@b.co", password: "lettuce harbour spoon" }));
    await waitFor(() => expect(result.current.account?.email).toBe("a@b.co"));
    window.dispatchEvent(new Event("pagehide"));
    stop();

    expect(localStorage.getItem(STORAGE_KEY)).toContain("a@b.co");
    expect(localStorage.getItem(STORAGE_KEY)).not.toContain("K7QM");
  });
});
