import { LogOut, UserRound } from "lucide-react";
import { useState } from "react";

import { AppLink } from "@/components/AppLink";
import { AuthDialog, type AuthMode } from "@/components/AuthDialog";
import { RecoveryCodeDialog } from "@/components/RecoveryCodeDialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { usePathname } from "@/lib/location";
import { cn } from "@/lib/utils";
import type { Account } from "@/api/types";
import type { Credentials, RecoveryRequest } from "@/hooks/useAccount";

/**
 * Who is signed in, at the foot of the sidebar: a guest is invited to sign
 * up (keeping what they made), an account gets its Account page and a way
 * out. The email is on the Account page, and on hover over its link.
 */
export function AccountBar({
  account,
  onSignUp,
  onLogIn,
  onRecover,
  onLogOut,
  loggingOut,
}: {
  account: Account | null;
  /** Resolves with the new account's recovery code. */
  onSignUp: (credentials: Credentials) => Promise<string>;
  onLogIn: (credentials: Credentials) => Promise<unknown>;
  /** Resolves with the next recovery code. */
  onRecover: (request: RecoveryRequest) => Promise<string>;
  onLogOut: () => Promise<unknown>;
  loggingOut: boolean;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const onAccountPage = usePathname() === "/account";
  const [mode, setMode] = useState<AuthMode>("signup");
  // A code just issued, and why: shown once, until saved.
  const [issued, setIssued] = useState<{ code: string; reason: string } | null>(null);

  const open = (next: AuthMode) => {
    setMode(next);
    setDialogOpen(true);
  };

  if (!account) return <div className="h-7" aria-hidden />;

  // Your data and deleting it. An icon in a phone's top bar, where space is
  // short; named in the sidebar.
  const accountLink = (
    <AppLink
      to="/account"
      aria-label="Account"
      title={account.email ?? undefined}
      aria-current={onAccountPage ? "page" : undefined}
      className={cn(
        buttonVariants({ variant: "ghost", size: "sm" }),
        "aria-[current=page]:bg-muted lg:justify-start",
      )}
    >
      <UserRound aria-hidden />
      <span className="hidden lg:inline">Account</span>
    </AppLink>
  );

  // A row in a phone's top bar; a stack at the foot of the sidebar. The
  // explanatory text only fits, and only helps, in the sidebar.
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-sm lg:flex-col lg:items-stretch lg:gap-2">
      {account.is_guest ? (
        <>
          <p className="hidden text-muted-foreground lg:block">You're using a guest session.</p>
          <Button
            size="sm"
            aria-label="Sign up to keep your meals"
            onClick={() => open("signup")}
          >
            <span className="lg:hidden">Sign up</span>
            <span className="hidden lg:inline">Sign up to keep your meals</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => open("login")}>
            Log in
          </Button>
          {accountLink}
        </>
      ) : (
        <>
          {accountLink}
          <Button
            size="sm"
            variant="ghost"
            disabled={loggingOut}
            onClick={() => void onLogOut()}
            className="lg:justify-start"
          >
            <LogOut aria-hidden />
            Log out
          </Button>
        </>
      )}

      <AuthDialog
        open={dialogOpen}
        mode={mode}
        onModeChange={setMode}
        onOpenChange={setDialogOpen}
        onSubmit={async (chosen, { email, password, recoveryCode }) => {
          if (chosen === "login") return onLogIn({ email, password });
          if (chosen === "signup") {
            const code = await onSignUp({ email, password });
            setIssued({ code, reason: "Your account is ready." });
            return;
          }
          const code = await onRecover({ email, recoveryCode, newPassword: password });
          setIssued({
            code,
            reason: "Your password is reset, and the code you used no longer works.",
          });
        }}
      />
      <RecoveryCodeDialog
        code={issued?.code ?? null}
        reason={issued?.reason ?? ""}
        onDone={() => setIssued(null)}
      />
    </div>
  );
}
