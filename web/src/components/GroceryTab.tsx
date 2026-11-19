import { Check, Copy, Download, RotateCcw, ShoppingBasket } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { GroceryLine } from "@/api/types";
import { AppLink } from "@/components/AppLink";
import { Button, buttonVariants } from "@/components/ui/button";
import { useBasket } from "@/hooks/useBasket";
import { byAisle, listAsText } from "@/lib/aisles";
import { cn } from "@/lib/utils";

interface Props {
  weekStart: string;
  /** The week's list, or null while it loads. */
  lines: readonly GroceryLine[] | null;
  /** Nights planned this week, to tell an empty week from meals without ingredients. */
  plannedDays: number;
}

const keyOf = (line: GroceryLine) => `${line.name}|${line.unit}`;

/**
 * The week's shopping, made for the shop: grouped by aisle, so the list is
 * walked once; tick an item and it drops into the basket below, so the next
 * thing to find is always at the top, and "how much is left" is one number.
 */
export function GroceryTab({ weekStart, lines, plannedDays }: Props) {
  const basket = useBasket(weekStart);
  const [copied, setCopied] = useState(false);

  // Ticking moves an item to the other list. Without this, keyboard focus
  // would vanish with it; instead it moves to the item that took its place.
  const boxes = useRef(new Map<string, HTMLInputElement>());
  const [focusNext, setFocusNext] = useState<string | null>(null);
  useEffect(() => {
    if (focusNext === null) return;
    boxes.current.get(focusNext)?.focus();
    setFocusNext(null);
  }, [focusNext]);

  if (lines === null) {
    return (
      <p role="status" className="py-10 text-sm text-muted-foreground">
        Loading the list…
      </p>
    );
  }

  if (lines.length === 0) {
    return plannedDays === 0 ? (
      <EmptyState
        message="Nothing is planned this week, so there is nothing to buy yet."
        action={{ to: "/plan", label: "Plan the week" }}
      />
    ) : (
      <EmptyState
        message="The meals planned this week have no ingredients yet, so there is nothing to buy."
        action={{ to: "/meals", label: "Add ingredients" }}
      />
    );
  }

  // In aisle order, so the next item down the list is the next one along
  // the shop, and focus moves the way the eye does.
  const ordered = byAisle(lines).flatMap((aisle) => aisle.lines);
  const toGet = ordered.filter((line) => !basket.keys.has(keyOf(line)));
  const inBasket = ordered.filter((line) => basket.keys.has(keyOf(line)));
  const aisles = byAisle(toGet);
  const done = inBasket.length;

  const toggle = (line: GroceryLine) => {
    const key = keyOf(line);
    const from = basket.keys.has(key) ? inBasket : toGet;
    const index = from.findIndex((l) => keyOf(l) === key);
    const rest = from.filter((l) => keyOf(l) !== key);
    const next = rest[Math.min(index, rest.length - 1)];
    setFocusNext(next ? keyOf(next) : key);
    basket.toggle(key);
  };

  // What is left is what someone else at the shop needs; before anything is
  // ticked, that is the whole list.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(listAsText(toGet));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked; the list is still on screen.
      setCopied(false);
    }
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([listAsText(ordered)], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `grocery-list-${weekStart}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const row = (line: GroceryLine, ticked: boolean) => {
    const key = keyOf(line);
    return (
      <li key={key}>
        <label className="relative flex min-h-12 cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/50 has-[:focus-visible]:bg-muted/50 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-inset">
          {/* A real checkbox, invisible and stretched over the whole row, so
              the row is one big target and every way of ticking it (tap,
              click, Space) goes to the checkbox itself. */}
          <input
            ref={(box) => {
              if (box) boxes.current.set(key, box);
              else boxes.current.delete(key);
            }}
            type="checkbox"
            checked={ticked}
            onChange={() => toggle(line)}
            className="peer absolute inset-0 size-full cursor-pointer appearance-none opacity-0"
          />
          <span
            aria-hidden
            className="grid size-5 shrink-0 place-items-center rounded-md border border-muted-foreground/50 transition-colors peer-checked:border-primary peer-checked:bg-primary"
          >
            {ticked && <Check className="size-3.5 text-primary-foreground" />}
          </span>
          <span className={cn("min-w-0 flex-1", ticked && "text-muted-foreground line-through")}>
            {line.name}
          </span>{" "}
          <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
            {line.display}
          </span>
        </label>
      </li>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border bg-card p-4 sm:p-5">
        <div className="min-w-56 flex-1">
          <p aria-live="polite" className="flex items-baseline gap-2">
            <span className="font-heading text-3xl font-semibold tabular-nums">{done}</span>
            <span className="text-sm text-muted-foreground">
              of {lines.length} in the basket
            </span>
          </p>
          <div aria-hidden className="mt-3 h-2 max-w-md overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${(done / lines.length) * 100}%` }}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {done > 0 && (
            <Button variant="ghost" onClick={basket.empty}>
              <RotateCcw aria-hidden />
              Start again
            </Button>
          )}
          {toGet.length > 0 && (
            <Button variant="outline" onClick={copy}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? "Copied" : done ? "Copy what's left" : "Copy"}
            </Button>
          )}
          {/* A text file is for a computer; on a phone, Copy is the way to
              send the list on, and the row stays on one line. */}
          <Button variant="outline" onClick={download} className="hidden sm:inline-flex">
            <Download aria-hidden />
            Download
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,44rem)_minmax(0,26rem)]">
        <section aria-labelledby="to-get">
          <h2 id="to-get" className="flex items-baseline gap-2 text-base font-semibold">
            To get
            <span className="text-sm font-normal text-muted-foreground tabular-nums">
              {toGet.length}
            </span>
          </h2>
          {aisles.length > 1 ? (
            <div className="mt-2 divide-y overflow-hidden rounded-xl border bg-card">
              {aisles.map((aisle) => {
                const headingId = `aisle-${aisle.category ?? "other"}`;
                return (
                  <div key={headingId} role="group" aria-labelledby={headingId}>
                    <h3
                      id={headingId}
                      className="border-b bg-muted/40 px-4 py-1.5 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                    >
                      {aisle.label}
                    </h3>
                    <ul className="divide-y">{aisle.lines.map((line) => row(line, false))}</ul>
                  </div>
                );
              })}
            </div>
          ) : toGet.length ? (
            // One aisle (or none the catalogue knows): a heading would say nothing.
            <ul className="mt-2 divide-y overflow-hidden rounded-xl border bg-card">
              {toGet.map((line) => row(line, false))}
            </ul>
          ) : (
            <p className="mt-2 rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
              That's everything. Enjoy the cooking.
            </p>
          )}
        </section>

        {inBasket.length > 0 && (
          <section aria-labelledby="in-basket">
            <h2 id="in-basket" className="flex items-baseline gap-2 text-base font-semibold">
              In the basket
              <span className="text-sm font-normal text-muted-foreground tabular-nums">
                {inBasket.length}
              </span>
            </h2>
            <ul className="mt-2 divide-y overflow-hidden rounded-xl border bg-card/50">
              {inBasket.map((line) => row(line, true))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function EmptyState({ message, action }: { message: string; action: { to: string; label: string } }) {
  return (
    <div className="flex max-w-md flex-col items-start gap-4 rounded-xl border border-dashed px-6 py-8">
      <ShoppingBasket aria-hidden className="size-8 text-muted-foreground/60" />
      <p className="text-sm text-muted-foreground">{message}</p>
      <AppLink to={action.to} className={buttonVariants()}>
        {action.label}
      </AppLink>
    </div>
  );
}
