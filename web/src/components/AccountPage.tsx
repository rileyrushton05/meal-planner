import { Download, LoaderCircle, Trash2, UserRound } from "lucide-react";
import { type FormEvent, useState } from "react";

import { ApiError } from "@/api/client";
import type { Account, AccountExport } from "@/api/types";
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

interface Props {
  account: Account;
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
export function AccountPage({ account, onExport, onDelete }: Props) {
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
      link.download = `meal-planner-export-${toIso(new Date())}.json`;
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

function DeleteSection({ account, onDelete }: Pick<Props, "account" | "onDelete">) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsPassword = !account.is_guest && account.email !== null;

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
      await onDelete(needsPassword ? password : undefined);
      reset(false);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "That didn't work. Nothing was deleted.",
      );
    } finally {
      setBusy(false);
    }
  };

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

      <AlertDialog open={open} onOpenChange={reset}>
        <AlertDialogTrigger render={<Button variant="destructive" />}>
          <Trash2 aria-hidden />
          {needsPassword ? "Delete account" : "Delete everything"}
        </AlertDialogTrigger>
        <AlertDialogContent>
          <form onSubmit={confirm} className="grid gap-4">
            <AlertDialogHeader>
              <AlertDialogTitle>
                {needsPassword ? "Delete your account for good?" : "Delete everything for good?"}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {needsPassword
                  ? "Enter your password to confirm. Everything goes, now, and there's no getting it back."
                  : "Every meal and plan in this session goes, now, and there's no getting it back."}
              </AlertDialogDescription>
            </AlertDialogHeader>

            {needsPassword && (
              <div className="grid gap-1.5">
                <Label htmlFor="delete-password">Password</Label>
                <Input
                  id="delete-password"
                  type="password"
                  autoComplete="current-password"
                  autoFocus
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-invalid={error !== null || undefined}
                  aria-describedby={error ? "delete-error" : undefined}
                />
              </div>
            )}
            {error && (
              <p id="delete-error" role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <AlertDialogFooter>
              <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
              <Button
                type="submit"
                variant="destructive"
                disabled={busy || (needsPassword && password === "")}
              >
                {busy && <LoaderCircle aria-hidden className="animate-spin" />}
                Delete for good
              </Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
