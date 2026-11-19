import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * What the page shows if it crashes, instead of going blank. Everything is
 * saved as you go, so reloading loses nothing that was already saved.
 *
 * `reference` is the error report's id when one was sent, so someone
 * describing the problem can point at the exact report.
 */
export function CrashScreen({ reference }: { reference?: string | null }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-background px-4 py-10 text-foreground">
      <div role="alert" className="grid max-w-sm justify-items-center gap-4 text-center">
        <img src="/favicon.svg" alt="" width={48} height={48} className="size-12" />
        <div className="grid gap-1.5">
          <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">
            The page hit a problem it couldn't recover from. Anything you'd already saved is safe;
            reloading usually fixes it.
          </p>
        </div>
        <Button onClick={() => window.location.reload()}>
          <RotateCw aria-hidden />
          Reload the page
        </Button>
        {reference && (
          <p className="text-xs text-muted-foreground">
            Reference: <span className="font-mono select-all">{reference.slice(0, 8)}</span>
          </p>
        )}
      </div>
    </main>
  );
}
