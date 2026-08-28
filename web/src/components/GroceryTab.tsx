import { Check, Copy, Download, ShoppingBasket } from "lucide-react";
import { useState } from "react";

import type { GroceryLine } from "@/api/types";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/dates";

interface Props {
  weekStart: string;
  lines: GroceryLine[] | null;
  busy: boolean;
  onGenerate: () => void;
}

export function GroceryTab({ weekStart, lines, busy, onGenerate }: Props) {
  const [copied, setCopied] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const asText = (lines ?? [])
    .map((line) => `- ${line.name}: ${line.display}`)
    .join("\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked; the list is still on screen.
      setCopied(false);
    }
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([asText], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `grocery-list-${weekStart}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const toggle = (key: string) =>
    setChecked((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Grocery list</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {lines?.length
              ? `${lines.length} item${lines.length === 1 ? "" : "s"} · ${checked.size} in the basket`
              : `Everything planned for the week of ${formatDate(weekStart)}`}
          </p>
        </div>
        <div className="flex gap-2">
          {lines && lines.length > 0 && (
            <>
              <Button variant="outline" onClick={copy}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button variant="outline" onClick={download}>
                <Download className="size-4" />
                Download
              </Button>
            </>
          )}
          <Button disabled={busy} onClick={onGenerate}>
            {lines ? "Regenerate" : "Generate list"}
          </Button>
        </div>
      </div>

      {lines === null || lines.length === 0 ? (
        <EmptyState
          message={
            lines === null
              ? "Generate a list to see everything you need this week."
              : "No meals assigned this week yet."
          }
        />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {lines.map((line) => {
            const key = `${line.name}-${line.unit}`;
            const done = checked.has(key);
            return (
              <li key={key}>
                {/* Ticking items off is local to the browser: a shopping aid,
                    not something worth a round trip or a database column. */}
                <button
                  onClick={() => toggle(key)}
                  aria-pressed={done}
                  className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                    done
                      ? "border-transparent bg-card/40 text-muted-foreground"
                      : "bg-card hover:border-primary/40 hover:bg-accent/40"
                  }`}
                >
                  <span
                    className={`flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                      done ? "border-primary bg-primary" : "border-muted-foreground/40"
                    }`}
                  >
                    {done && (
                      <Check className="size-3.5 text-primary-foreground" />
                    )}
                  </span>
                  <span className={`flex-1 text-sm ${done ? "line-through" : ""}`}>
                    {line.name}
                  </span>
                  <span className="font-mono text-sm tabular-nums text-muted-foreground">
                    {line.display}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center">
      <ShoppingBasket className="size-8 text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
