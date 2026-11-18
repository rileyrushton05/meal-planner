/**
 * Who is signed in, and signing up, in and out.
 *
 * Everything cached belongs to one account, so whenever the account on
 * screen changes the cache is reset and refetched: after logging in (a
 * different account's meals), after logging out (a new guest), and when a
 * session ends mid-use and the client starts a new guest session
 * (`onGuestSessionStarted`). Signing up is the exception: a guest who signs
 * up keeps the same account and data, so only the name on it changes.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, onGuestSessionStarted } from "../api/client";
import { queryKeys } from "../api/queryClient";
import type { Account, SignedUp } from "../api/types";

export type Credentials = { email: string; password: string };
export type RecoveryRequest = { email: string; recoveryCode: string; newPassword: string };

export const ACCOUNT_DELETED_NOTICE =
  "Your account and everything in it have been deleted. You're in a new guest session.";
export const GUEST_DELETED_NOTICE =
  "Everything from that guest session has been deleted. You're starting afresh.";

export const SESSION_ENDED_NOTICE =
  "Your session ended, so you're in a new guest session. " +
  "Log in to get back to your account.";

export function useAccount() {
  const queryClient = useQueryClient();
  const account = useQuery({ queryKey: queryKeys.account, queryFn: api.me });
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(
    () =>
      onGuestSessionStarted(() => {
        // On a first visit nothing is cached yet, so there is nothing to
        // undo. With data on screen, the session it came from has ended.
        if (queryClient.getQueryData(queryKeys.library) === undefined) return;
        setNotice(SESSION_ENDED_NOTICE);
        void queryClient.resetQueries();
      }),
    [queryClient],
  );

  /** Another account's data is about to be on screen. */
  const startOver = async () => {
    setNotice(null);
    await queryClient.resetQueries();
  };

  // The recovery code is handed back to the caller to show, and kept out
  // of the cache: once shown, it should exist nowhere in the app.
  const signUp = useMutation({
    mutationFn: ({ email, password }: Credentials) => api.signUp(email, password),
    onSuccess: ({ recovery_code: _shown, ...account }) =>
      queryClient.setQueryData<Account>(queryKeys.account, account),
  });

  // Possibly a different account from the one on screen (a guest who
  // remembered they had one), so everything is fetched again.
  const recover = useMutation({
    mutationFn: ({ email, recoveryCode, newPassword }: RecoveryRequest) =>
      api.recover(email, recoveryCode, newPassword),
    onSuccess: startOver,
  });

  const replaceRecoveryCode = useMutation({
    mutationFn: (password: string) => api.replaceRecoveryCode(password),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.account }),
  });

  const logIn = useMutation({
    mutationFn: ({ email, password }: Credentials) => api.logIn(email, password),
    onSuccess: startOver,
  });

  const logOut = useMutation({ mutationFn: api.logOut, onSuccess: startOver });

  // Gone for good: whatever is cached belongs to no one now. The next
  // request finds no session and starts a guest, as on a first visit.
  const deleteAccount = useMutation({
    mutationFn: (password?: string) => api.deleteAccount(password),
    onSuccess: async () => {
      const wasGuest = account.data?.is_guest ?? true;
      await startOver();
      setNotice(wasGuest ? GUEST_DELETED_NOTICE : ACCOUNT_DELETED_NOTICE);
    },
  });

  return {
    account: account.data ?? null,
    notice,
    dismissNotice: () => setNotice(null),
    /** Resolves with the new account's recovery code, to show once. */
    signUp: (credentials: Credentials): Promise<string> =>
      signUp.mutateAsync(credentials).then((signedUp: SignedUp) => signedUp.recovery_code),
    /** Resolves with the next recovery code, to show once. */
    recover: (request: RecoveryRequest): Promise<string> =>
      recover.mutateAsync(request).then((signedIn) => signedIn.recovery_code),
    /** Resolves with the new recovery code, to show once. */
    replaceRecoveryCode: (password: string): Promise<string> =>
      replaceRecoveryCode.mutateAsync(password).then((made) => made.recovery_code),
    logIn: (credentials: Credentials): Promise<void> =>
      logIn.mutateAsync(credentials).then(() => undefined),
    logOut: (): Promise<void> => logOut.mutateAsync(),
    loggingOut: logOut.isPending,
    /** Resolves once deleted; rejects with the reason, such as a wrong password. */
    deleteAccount: (password?: string): Promise<void> => deleteAccount.mutateAsync(password),
    exportAccount: api.exportAccount,
  };
}
