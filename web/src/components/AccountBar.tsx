import { ChevronsUpDown, LogIn, LogOut, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";

import { AppLink } from "@/components/AppLink";
import { AuthDialog, type AuthMode } from "@/components/AuthDialog";
import { RecoveryCodeDialog } from "@/components/RecoveryCodeDialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLinkItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { usePathname } from "@/lib/location";
import type { Account } from "@/api/types";
import type { Credentials, RecoveryRequest } from "@/hooks/useAccount";

/**
 * Who is signed in, at the foot of the sidebar (in a phone's top bar).
 *
 * A guest is invited to sign up, keeping what they made: a card in the
 * sidebar, a single button on a phone. Below it, one row says who you are
 * and opens a menu: your Account page, Privacy, and logging in or out. The
 * email itself is on the Account page, and on hover over the row.
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
  const [mode, setMode] = useState<AuthMode>("signup");
  // A code just issued, and why: shown once, until saved.
  const [issued, setIssued] = useState<{ code: string; reason: string } | null>(null);

  const open = (next: AuthMode) => {
    setMode(next);
    setDialogOpen(true);
  };

  if (!account) return <div className="size-9" aria-hidden />;

  return (
    <div className="flex min-w-0 items-center gap-2 lg:flex-col lg:items-stretch lg:gap-3">
      {account.is_guest && (
        <section
          aria-label="Keep your meals"
          className="lg:grid lg:gap-2 lg:rounded-xl lg:border lg:bg-card lg:p-3"
        >
          <h2 className="hidden text-sm font-semibold lg:block">Keep your meals</h2>
          <p className="hidden text-xs leading-relaxed text-muted-foreground lg:block">
            Sign up to keep them on every device. Guests unused for 30 days are deleted.
          </p>
          <div className="flex gap-1.5 lg:mt-1">
            <Button
              size="sm"
              aria-label="Sign up to keep your meals"
              onClick={() => open("signup")}
              className="lg:flex-1"
            >
              Sign up
            </Button>
            {/* On a phone, logging in is in the menu: the top bar has no room. */}
            <Button
              size="sm"
              variant="outline"
              onClick={() => open("login")}
              className="hidden lg:inline-flex"
            >
              Log in
            </Button>
          </div>
        </section>
      )}

      <AccountMenu
        account={account}
        onLogIn={() => open("login")}
        onLogOut={() => void onLogOut()}
        loggingOut={loggingOut}
      />

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

/**
 * The row that says who you are, and the menu it opens. In the sidebar the
 * row is named ("Guest, Not signed in"); on a phone it is just the avatar,
 * and the same words are its accessible name.
 */
function AccountMenu({
  account,
  onLogIn,
  onLogOut,
  loggingOut,
}: {
  account: Account;
  onLogIn: () => void;
  onLogOut: () => void;
  loggingOut: boolean;
}) {
  const path = usePathname();
  const guest = account.is_guest;
  const initial = account.email?.trim().charAt(0).toUpperCase();

  return (
    <div className={guest ? "lg:border-t lg:pt-3" : undefined}>
      <DropdownMenu>
        <DropdownMenuTrigger
          title={account.email ?? undefined}
          className="flex items-center gap-2.5 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring lg:w-full lg:rounded-lg lg:p-1.5 lg:text-left lg:hover:bg-sidebar-accent lg:data-popup-open:bg-sidebar-accent"
        >
          <span
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-full bg-sidebar-accent text-sm font-semibold text-muted-foreground lg:size-8"
          >
            {initial ?? <UserRound className="size-4" />}
          </span>
          <span className="sr-only min-w-0 flex-1 lg:not-sr-only lg:grid lg:leading-tight">
            <span className="truncate text-sm font-semibold">{guest ? "Guest" : "Account"}</span>{" "}
            <span className="truncate text-xs text-muted-foreground">
              {guest ? "Not signed in" : "Signed in"}
            </span>
          </span>
          <ChevronsUpDown aria-hidden className="hidden size-4 text-muted-foreground lg:block" />
        </DropdownMenuTrigger>

        {/* Above the row in the sidebar; flips below the avatar on a phone,
            where there is no room above. */}
        <DropdownMenuContent side="top" align="start" className="lg:w-(--anchor-width)">
          <DropdownMenuLinkItem
            closeOnClick
            render={<AppLink to="/account" />}
            aria-current={path === "/account" ? "page" : undefined}
          >
            <UserRound aria-hidden />
            Account
          </DropdownMenuLinkItem>
          <DropdownMenuLinkItem
            closeOnClick
            render={<AppLink to="/privacy" />}
            aria-current={path === "/privacy" ? "page" : undefined}
          >
            <ShieldCheck aria-hidden />
            Privacy
          </DropdownMenuLinkItem>
          <DropdownMenuSeparator />
          {guest ? (
            <DropdownMenuItem onClick={onLogIn}>
              <LogIn aria-hidden />
              Log in
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem disabled={loggingOut} onClick={onLogOut}>
              <LogOut aria-hidden />
              Log out
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
