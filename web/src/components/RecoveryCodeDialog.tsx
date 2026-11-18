import { Check, Copy, Download, KeyRound } from "lucide-react";
import { useId, useState } from "react";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { toIso } from "@/lib/dates";

/**
 * A recovery code, shown the one time it exists outside the person's own
 * keeping. The server stores only a hash, so this is the only copy.
 *
 * It does not close until the person says they have saved it: a code
 * dismissed by a stray click is an account that cannot be recovered. Copy
 * and Download are right there, so saving it is one click.
 */
export function RecoveryCodeDialog({
  code,
  reason,
  onDone,
}: {
  /** The code to show; the dialog is open while there is one. */
  code: string | null;
  /** Why there is a code now: a new account, a replaced code... */
  reason: string;
  onDone: () => void;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const checkbox = useId();

  const finish = () => {
    setSaved(false);
    setCopied(false);
    onDone();
  };

  const copy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // Clipboard access can be blocked; the code is on screen to copy.
    }
  };

  const download = () => {
    if (!code) return;
    const text =
      `Meal Planner recovery code\n\n${code}\n\n` +
      "If you forget your password, use this code to set a new one.\n" +
      "It works once; you will be given a new one when you use it.\n";
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `meal-planner-recovery-code-${toIso(new Date())}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AlertDialog
      open={code !== null}
      // Escape and outside clicks do nothing until it has been saved.
      onOpenChange={(open) => {
        if (!open && saved) finish();
      }}
    >
      <AlertDialogContent className="data-[size=default]:sm:max-w-md">
        <AlertDialogHeader>
          <span className="mx-auto grid size-10 place-items-center rounded-full bg-primary-subtle text-primary-subtle-foreground sm:mx-0">
            <KeyRound aria-hidden className="size-5" />
          </span>
          <AlertDialogTitle>Save your recovery code</AlertDialogTitle>
          <AlertDialogDescription>
            {reason} If you forget your password, this code is the only way back in. It's
            shown once: we keep only a scrambled copy, so we can't show it again.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <p
          aria-label="Recovery code"
          className="rounded-lg border bg-muted/50 px-4 py-3 text-center font-mono text-lg font-semibold tracking-wider select-all"
        >
          {code}
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={copy}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="outline" onClick={download}>
            <Download aria-hidden />
            Download
          </Button>
        </div>

        <label htmlFor={checkbox} className="flex items-start gap-2.5 text-sm">
          <input
            id={checkbox}
            type="checkbox"
            checked={saved}
            onChange={(e) => setSaved(e.target.checked)}
            className="mt-0.5 size-4 accent-primary"
          />
          I've saved it somewhere safe, like a password manager.
        </label>

        <AlertDialogFooter>
          <Button disabled={!saved} onClick={finish}>
            Done
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
