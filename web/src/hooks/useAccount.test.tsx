import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { createQueryClient, queryKeys } from "@/api/queryClient";
import { SESSION_ENDED_NOTICE, useAccount } from "@/hooks/useAccount";

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
    queryClient.setQueryData(queryKeys.library, { meals: [], ingredient_names: [], templates: [] });

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
