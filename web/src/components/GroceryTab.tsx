import {
  ArrowDownUp,
  Check,
  Copy,
  Download,
  EllipsisVertical,
  House,
  ListPlus,
  RotateCcw,
  ShoppingBasket,
  Star,
  Trash2,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Category, CheckState, GroceryLine, GroceryList } from "@/api/types";
import { AppLink } from "@/components/AppLink";
import { AddItemForm } from "@/components/groceries/AddItemForm";
import { AisleOrderDialog } from "@/components/groceries/AisleOrderDialog";
import { UsualsDialog } from "@/components/groceries/UsualsDialog";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { byAisle, listAsText } from "@/lib/aisles";
import { cn } from "@/lib/utils";

/** What the page can do to the week's list; each is saved for the week shown. */
export interface GroceryActions {
  onCheck: (key: string, state: CheckState | null) => void;
  onEmptyBasket: () => void;
  /** Resolves true once added. */
  onAddExtra: (text: string) => Promise<boolean>;
  onRemoveExtra: (extraId: number) => void;
  onKeepExtra: (extraId: number) => void;
  onAddUsuals: () => void;
  /** Resolves true once added. */
  onAddUsual: (text: string) => Promise<boolean>;
  onRemoveUsual: (id: number) => void;
  onAisleOrder: (order: Category[]) => void;
}

interface Props extends GroceryActions {
  weekStart: string;
  /** The week's list, or null while it loads. */
  list: GroceryList | null;
  /** Nights planned this week, to tell an empty week from meals without ingredients. */
  plannedDays: number;
  pending: boolean;
}

/**
 * The week's shopping, made for the shop: grouped by aisle in the order of
 * the person's own shop, so the list is walked once; tick an item and it
 * drops into the basket, so the next thing to find is always at the top,
 * and "how much is left" is one number. Ticks are saved to the account, so
 * the phone in the shop and the laptop at home show the same list.
 */
export function GroceryTab({ weekStart, list, plannedDays, pending, ...actions }: Props) {
  const [copied, setCopied] = useState(false);
  const [usualsOpen, setUsualsOpen] = useState(false);
  const [orderOpen, setOrderOpen] = useState(false);

  // Ticks made here, shown before the list comes back with them. The cache
  // has them at once, but hands React the change a moment later, and in
  // that moment a controlled checkbox snaps back: a flicker, and a row that
  // moves after the tick rather than with it. Each new list from the cache
  // (which includes these ticks, or the server's word on them) replaces them.
  const [ticked, setTicked] = useState({ list, states: new Map<string, CheckState | null>() });
  let local = ticked;
  if (ticked.list !== list) {
    local = { list, states: new Map() };
    setTicked(local);
  }

  // Ticking moves an item to another list. Without this, keyboard focus
  // would vanish with it; instead it moves to the item that took its place.
  const boxes = useRef(new Map<string, HTMLInputElement>());
  const [focusNext, setFocusNext] = useState<string | null>(null);
  useEffect(() => {
    if (focusNext === null) return;
    boxes.current.get(focusNext)?.focus();
    setFocusNext(null);
  }, [focusNext]);

  if (list === null) {
    return (
      <p role="status" className="py-10 text-sm text-muted-foreground">
        Loading the list…
      </p>
    );
  }

  const order = list.aisle_order;
  const lines = list.lines.map((line) =>
    local.states.has(line.key) ? { ...line, state: local.states.get(line.key) ?? null } : line,
  );
  // In aisle order, so the next item down the list is the next one along
  // the shop, and focus moves the way the eye does.
  const ordered = byAisle(lines, order).flatMap((aisle) => aisle.lines);
  const toGet = ordered.filter((line) => line.state === null);
  const inBasket = ordered.filter((line) => line.state === "basket");
  const atHome = ordered.filter((line) => line.state === "have");
  const toBuy = toGet.length + inBasket.length;
  const done = inBasket.length;
  const aisles = byAisle(toGet, order);

  const extraNames = new Set(
    list.lines.filter((l) => l.extra_id !== null).map((l) => l.name.toLowerCase()),
  );
  const usualNames = new Set(list.usuals.map((u) => u.name.toLowerCase()));
  const usualsMissing = list.usuals.filter((u) => !extraNames.has(u.name.toLowerCase())).length;

  /** Move a line, keeping keyboard focus in the list it left. */
  const mark = (line: GroceryLine, state: CheckState | null) => {
    const from = ordered.filter((l) => l.state === line.state);
    const index = from.findIndex((l) => l.key === line.key);
    const rest = from.filter((l) => l.key !== line.key);
    const next = rest[Math.min(index, rest.length - 1)];
    setFocusNext(next ? next.key : line.key);
    setTicked({ list, states: new Map(local.states).set(line.key, state) });
    actions.onCheck(line.key, state);
  };

  // What is left is what someone else at the shop needs; before anything is
  // ticked, that is the whole list.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(listAsText(toGet, order));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked; the list is still on screen.
      setCopied(false);
    }
  };

  const download = () => {
    const text = listAsText([...toGet, ...inBasket], order);
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `grocery-list-${weekStart}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const menu = (line: GroceryLine) => {
    const extra = line.extra_id;
    if (line.state !== null && extra === null) return null;
    const kept = usualNames.has(line.name.toLowerCase());
    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`More for ${line.name}`}
          className={cn(buttonVariants({ variant: "ghost", size: "icon" }), "mr-2 shrink-0")}
        >
          <EllipsisVertical aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {line.state === null && (
            <DropdownMenuItem onClick={() => mark(line, "have")}>
              <House aria-hidden />
              Already have it
            </DropdownMenuItem>
          )}
          {extra !== null && (
            <>
              {line.state === null && <DropdownMenuSeparator />}
              <DropdownMenuItem disabled={kept} onClick={() => actions.onKeepExtra(extra)}>
                <Star aria-hidden />
                {kept ? "One of your usuals" : "Keep as a usual"}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => actions.onRemoveExtra(extra)}>
                <Trash2 aria-hidden />
                Remove from the list
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  const row = (line: GroceryLine) => {
    const ticked = line.state === "basket";
    return (
      <li
        key={line.key}
        className="flex items-center transition-colors hover:bg-muted/50 has-[:focus-visible]:bg-muted/50"
      >
        <label className="relative flex min-h-12 min-w-0 flex-1 cursor-pointer items-center gap-3 py-2.5 pr-2 pl-4 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-inset">
          {/* A real checkbox, invisible and stretched over the whole row, so
              the row is one big target and every way of ticking it (tap,
              click, Space) goes to the checkbox itself. */}
          <input
            ref={(box) => {
              if (box) boxes.current.set(line.key, box);
              else boxes.current.delete(line.key);
            }}
            type="checkbox"
            checked={ticked}
            onChange={() => mark(line, ticked ? null : "basket")}
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
            {line.extra_id !== null && (
              <>
                {" "}
                <span className="ml-1 text-xs text-muted-foreground">extra</span>
              </>
            )}
          </span>{" "}
          <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
            {line.display}
          </span>
        </label>
        {menu(line)}
      </li>
    );
  };

  const addPanel = (
    <section aria-label="Add to the list" className="space-y-3 rounded-xl border bg-card p-4">
      <AddItemForm label="Add something else" pending={pending} onAdd={actions.onAddExtra} />
      <div className="flex flex-wrap gap-2">
        {usualsMissing > 0 && (
          <Button variant="secondary" size="sm" disabled={pending} onClick={actions.onAddUsuals}>
            <ListPlus aria-hidden />
            {usualsMissing === list.usuals.length
              ? `Add my ${usualsMissing === 1 ? "usual" : `${usualsMissing} usuals`}`
              : `Add the other ${usualsMissing === 1 ? "usual" : `${usualsMissing} usuals`}`}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => setUsualsOpen(true)}>
          <Star aria-hidden />
          My usuals
          {list.usuals.length > 0 && (
            <span className="text-muted-foreground tabular-nums">{list.usuals.length}</span>
          )}
        </Button>
      </div>
    </section>
  );

  const dialogs = (
    <>
      <UsualsDialog
        open={usualsOpen}
        onOpenChange={setUsualsOpen}
        usuals={list.usuals}
        pending={pending}
        onAdd={actions.onAddUsual}
        onRemove={actions.onRemoveUsual}
      />
      <AisleOrderDialog
        open={orderOpen}
        onOpenChange={setOrderOpen}
        order={order}
        onSave={actions.onAisleOrder}
      />
    </>
  );

  if (list.lines.length === 0) {
    return (
      <div className="grid max-w-md gap-6">
        {plannedDays === 0 ? (
          <EmptyState
            message="Nothing is planned this week, so there is nothing to buy yet."
            action={{ to: "/plan", label: "Plan the week" }}
          />
        ) : (
          <EmptyState
            message="The meals planned this week have no ingredients yet, so there is nothing to buy."
            action={{ to: "/meals", label: "Add ingredients" }}
          />
        )}
        {addPanel}
        {dialogs}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border bg-card p-4 sm:p-5">
        <div className="min-w-56 flex-1">
          <p aria-live="polite" className="flex items-baseline gap-2">
            <span className="font-heading text-3xl font-semibold tabular-nums">{done}</span>
            <span className="text-sm text-muted-foreground">of {toBuy} in the basket</span>
          </p>
          <div aria-hidden className="mt-3 h-2 max-w-md overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${toBuy ? (done / toBuy) * 100 : 0}%` }}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {done > 0 && (
            <Button variant="ghost" disabled={pending} onClick={actions.onEmptyBasket}>
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
          <div className="flex items-center justify-between gap-2">
            <h2 id="to-get" className="flex items-baseline gap-2 text-base font-semibold">
              To get
              <span className="text-sm font-normal text-muted-foreground tabular-nums">
                {toGet.length}
              </span>
            </h2>
            <Button variant="ghost" size="sm" onClick={() => setOrderOpen(true)}>
              <ArrowDownUp aria-hidden />
              Aisle order
            </Button>
          </div>
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
                    <ul className="divide-y">{aisle.lines.map(row)}</ul>
                  </div>
                );
              })}
            </div>
          ) : toGet.length ? (
            // One aisle (or none the catalogue knows): a heading would say nothing.
            <ul className="mt-2 divide-y overflow-hidden rounded-xl border bg-card">
              {toGet.map(row)}
            </ul>
          ) : (
            <p className="mt-2 rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
              That's everything. Enjoy the cooking.
            </p>
          )}
        </section>

        <div className="grid gap-6">
          {addPanel}

          {inBasket.length > 0 && (
            <section aria-labelledby="in-basket">
              <h2 id="in-basket" className="flex items-baseline gap-2 text-base font-semibold">
                In the basket
                <span className="text-sm font-normal text-muted-foreground tabular-nums">
                  {inBasket.length}
                </span>
              </h2>
              <ul className="mt-2 divide-y overflow-hidden rounded-xl border bg-card/50">
                {inBasket.map(row)}
              </ul>
            </section>
          )}

          {atHome.length > 0 && (
            <section aria-labelledby="at-home">
              <h2 id="at-home" className="flex items-baseline gap-2 text-base font-semibold">
                Already have
                <span className="text-sm font-normal text-muted-foreground tabular-nums">
                  {atHome.length}
                </span>
              </h2>
              <ul className="mt-2 divide-y overflow-hidden rounded-xl border bg-card/50">
                {atHome.map((line) => (
                  <li key={line.key} className="flex min-h-12 items-center gap-3 py-1.5 pr-2 pl-4">
                    <span className="min-w-0 flex-1 text-muted-foreground">{line.name}</span>
                    <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
                      {line.display}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Need ${line.name} after all`}
                      onClick={() => mark(line, null)}
                    >
                      <Undo2 aria-hidden />
                      Need it
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
      {dialogs}
    </div>
  );
}

function EmptyState({ message, action }: { message: string; action: { to: string; label: string } }) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-xl border border-dashed px-6 py-8">
      <ShoppingBasket aria-hidden className="size-8 text-muted-foreground/60" />
      <p className="text-sm text-muted-foreground">{message}</p>
      <AppLink to={action.to} className={buttonVariants()}>
        {action.label}
      </AppLink>
    </div>
  );
}
