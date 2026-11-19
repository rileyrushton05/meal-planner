import { Download, KeyRound, LoaderCircle, Trash2, TriangleAlert, UserRound } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import type { Account, AccountExport } from "@/api/types";
import { RecoveryCodeDialog } from "@/components/RecoveryCodeDialog";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toIso } from "@/lib/dates";
import { cn } from "@/lib/utils";

interface Props {
  account: Account;
  /** Resolves with the new recovery code. */
  onReplaceRecoveryCode: (password: string) => Promise<string>;
  onExport: () => Promise<AccountExport>;
  /** Resolves once deleted; rejects with the reason (a wrong password). */
  onDelete: (password?: string) => Promise<void>;
}

/**
 * Your account, and the two ways to leave with nothing left behind: take a
 * copy of everything, and delete it all. Deleting is last on the page and
 * the download is offered right beside it, so nobody deletes first and
 * wishes they had kept a copy.
 */
export function AccountPage({ account, onReplaceRecoveryCode, onExport, onDelete }: Props) {
  const hasLogin = !account.is_guest && account.email !== null;
  return (
    <div className="max-w-2xl space-y-6">
      <section aria-labelledby="who" className="flex items-center gap-4 rounded-xl border bg-card p-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary-subtle text-primary-subtle-foreground">
          <UserRound aria-hidden className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 id="who" className="text-base font-semibold">
            {account.is_guest ? "Guest session" : "Your account"}
          </h2>
          <p className="truncate text-sm text-muted-foreground">
            {account.is_guest
              ? "No email or password: your meals belong to this browser's session until you sign up."
              : account.email}
          </p>
        </div>
      </section>

      {hasLogin && (
        <RecoverySection hasCode={account.has_recovery_code} onReplace={onReplaceRecoveryCode} />
      )}
      <ExportSection onExport={onExport} />
      <DeleteSection account={account} onDelete={onDelete} />
    </div>
  );
}

function ExportSection({ onExport }: Pick<Props, "onExport">) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await onExport();
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `the-fridge-door-export-${toIso(new Date())}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The download didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="your-data" className="space-y-3 rounded-xl border bg-card p-5">
      <h2 id="your-data" className="text-base font-semibold">
        Your data
      </h2>
      <p className="text-sm text-muted-foreground">
        A copy of everything you've made: your meals with their ingredients, and every day
        you've planned, as a JSON file you can keep or open in another app.
      </p>
      <Button variant="outline" onClick={download} disabled={busy}>
        {busy ? <LoaderCircle aria-hidden className="animate-spin" /> : <Download aria-hidden />}
        Download my data
      </Button>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

function RecoverySection({
  hasCode,
  onReplace,
}: {
  hasCode: boolean;
  onReplace: (password: string) => Promise<string>;
}) {
  const [issued, setIssued] = useState<string | null>(null);

  return (
    <section
      aria-labelledby="recovery-code"
      className={cn(
        "space-y-3 rounded-xl border bg-card p-5",
        !hasCode && "border-amber-500/50",
      )}
    >
      <h2 id="recovery-code" className="flex items-center gap-2 text-base font-semibold">
        {hasCode ? (
          <KeyRound aria-hidden className="size-4 text-primary" />
        ) : (
          <TriangleAlert aria-hidden className="size-4 text-amber-600 dark:text-amber-400" />
        )}
        Recovery code
      </h2>
      <p className="text-sm text-muted-foreground">
        {hasCode
          ? "If you forget your password, your recovery code gets you back in. Lost it? Make a new one, and the old one stops working."
          : "You don't have a recovery code yet, so a forgotten password couldn't be recovered. Make one now and keep it somewhere safe."}
      </p>
      <PasswordDialog
        trigger={
          <>
            <KeyRound aria-hidden />
            {hasCode ? "Make a new recovery code" : "Make a recovery code"}
          </>
        }
        triggerVariant={hasCode ? "outline" : "default"}
        title={hasCode ? "Make a new recovery code?" : "Make a recovery code"}
        description={
          hasCode
            ? "Enter your password to confirm. Your current code will stop working."
            : "Enter your password to confirm."
        }
        confirmLabel="Make code"
        idPrefix="recovery"
        needsPassword
        onConfirm={async (password) => setIssued(await onReplace(password ?? ""))}
      />
      <RecoveryCodeDialog
        code={issued}
        reason={hasCode ? "Your old code no longer works." : "Your account can now be recovered."}
        onDone={() => setIssued(null)}
      />
    </section>
  );
}

function DeleteSection({ account, onDelete }: Pick<Props, "account" | "onDelete">) {
  const needsPassword = !account.is_guest && account.email !== null;

  return (
    <section
      aria-labelledby="delete-account"
      className="space-y-3 rounded-xl border border-destructive/40 bg-card p-5"
    >
      <h2 id="delete-account" className="text-base font-semibold">
        {needsPassword ? "Delete your account" : "Delete everything"}
      </h2>
      <p className="text-sm text-muted-foreground">
        {needsPassword
          ? "Deletes your account, every meal, ingredient and plan, and signs you out on every device. It can't be undone, so download your data first if you might want it."
          : "Deletes every meal, ingredient and plan in this guest session, and starts you afresh. It can't be undone."}
      </p>
      <PasswordDialog
        trigger={
          <>
            <Trash2 aria-hidden />
            {needsPassword ? "Delete account" : "Delete everything"}
          </>
        }
        triggerVariant="destructive"
        title={needsPassword ? "Delete your account for good?" : "Delete everything for good?"}
        description={
          needsPassword
            ? "Enter your password to confirm. Everything goes, now, and there's no getting it back."
            : "Every meal and plan in this session goes, now, and there's no getting it back."
        }
        confirmLabel="Delete for good"
        confirmVariant="destructive"
        idPrefix="delete"
        needsPassword={needsPassword}
        onConfirm={onDelete}
      />
    </section>
  );
}

/**
 * A button that opens a confirmation, asking for the password where there
 * is one. Stays open with the server's reason if it is refused (a wrong
 * password, a wait), and forgets what was typed when closed.
 */
function PasswordDialog({
  trigger,
  triggerVariant,
  title,
  description,
  confirmLabel,
  confirmVariant = "default",
  idPrefix,
  needsPassword,
  onConfirm,
}: {
  trigger: ReactNode;
  triggerVariant: "default" | "outline" | "destructive";
  title: string;
  description: string;
  confirmLabel: string;
  confirmVariant?: "default" | "destructive";
  idPrefix: string;
  needsPassword: boolean;
  onConfirm: (password?: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setPassword("");
      setError(null);
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onConfirm(needsPassword ? password : undefined);
      reset(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't work. Nothing changed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={reset}>
      <AlertDialogTrigger render={<Button variant={triggerVariant} />}>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <form onSubmit={confirm} className="grid gap-4">
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            <AlertDialogDescription>{description}</AlertDialogDescription>
          </AlertDialogHeader>

          {needsPassword && (
            <div className="grid gap-1.5">
              <Label htmlFor={`${idPrefix}-password`}>Password</Label>
              <Input
                id={`${idPrefix}-password`}
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error !== null || undefined}
                aria-describedby={error ? `${idPrefix}-error` : undefined}
              />
            </div>
          )}
          {error && (
            <p id={`${idPrefix}-error`} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <Button
              type="submit"
              variant={confirmVariant}
              disabled={busy || (needsPassword && password === "")}
            >
              {busy && <LoaderCircle aria-hidden className="animate-spin" />}
              {confirmLabel}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
