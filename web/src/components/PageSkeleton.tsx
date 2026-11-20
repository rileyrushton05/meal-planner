import { type ReactNode, useEffect, useState } from "react";

import { cn } from "@/lib/utils";

export type SkeletonPage = "home" | "meals" | "plan" | "groceries" | "account";

/** After this long, say why the wait: a server starting from cold. */
export const SLOW_LOAD_MS = 2500;

/**
 * The outline of the page about to appear, while there is nothing to show
 * yet: a first visit, or one with nothing kept from the last. Each follows
 * its page's real grid, so the content lands where the outline was rather
 * than shoving the page about, and the wait reads as the app loading
 * rather than as something broken.
 *
 * If it takes a while, it says why. The line for that is there from the
 * start, so the outline does not move when the words appear.
 */
export function PageSkeleton({ page }: { page: SkeletonPage }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_LOAD_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">Loading…</span>
      <p
        className={cn(
          "mb-4 min-h-10 text-sm text-muted-foreground transition-opacity duration-500 sm:min-h-5",
          slow ? "opacity-100" : "opacity-0",
        )}
      >
        {slow && "Waking the server up. After a quiet spell the first load takes a few seconds."}
      </p>
      <div aria-hidden="true">{OUTLINES[page]()}</div>
    </div>
  );
}

/** One grey shape. It pulses only for those who have not asked for less motion. */
function Bone({ className }: { className?: string }) {
  return <div className={cn("rounded-md bg-muted-foreground/15 motion-safe:animate-pulse", className)} />;
}

function Card({ className, children }: { className?: string; children?: ReactNode }) {
  return <div className={cn("rounded-xl border bg-card p-5", className)}>{children}</div>;
}

/** A list row: something to tick or a picture, a name, an amount. */
function Row({ lead = "circle" }: { lead?: "circle" | "box" }) {
  return (
    <div className="flex items-center gap-3 py-3">
      <Bone className={cn("size-5 shrink-0", lead === "circle" ? "rounded-full" : "rounded")} />
      <Bone className="h-4 flex-1" />
      <Bone className="h-4 w-12" />
    </div>
  );
}

const repeat = (count: number, render: (index: number) => ReactNode) =>
  Array.from({ length: count }, (_, index) => render(index));

const OUTLINES: Record<SkeletonPage, () => ReactNode> = {
  // ThisWeekPage: tonight beside the week's numbers, then the seven days.
  home: () => (
    <div className="space-y-8">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="space-y-6">
          <Bone className="h-4 w-40" />
          <div className="flex items-center gap-4">
            <Bone className="size-14 rounded-full" />
            <div className="flex-1 space-y-2">
              <Bone className="h-8 w-2/3 max-w-sm" />
              <Bone className="h-4 w-40" />
            </div>
          </div>
          <div className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
            {repeat(4, (i) => (
              <Row key={i} lead="box" />
            ))}
          </div>
        </Card>
        <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
          {repeat(3, (i) => (
            <Card key={i} className="space-y-3">
              <Bone className="h-4 w-24" />
              <Bone className="h-8 w-16" />
              <Bone className="h-4 w-32" />
            </Card>
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <Bone className="h-5 w-28" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 week:grid-cols-7">
          {repeat(7, (i) => (
            <Card key={i} className="h-24 space-y-3 p-4">
              <Bone className="h-3 w-14" />
              <Bone className="h-4 w-full" />
            </Card>
          ))}
        </div>
      </div>
    </div>
  ),

  // MealsTab: the list beside the open meal (the list alone on a phone).
  meals: () => (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,52rem)] lg:items-start">
      <Card className="space-y-1 p-3">
        <div className="flex gap-2 pb-2">
          <Bone className="h-9 flex-1" />
          <Bone className="h-9 w-28" />
        </div>
        {repeat(4, (i) => (
          <div key={i} className="flex items-center gap-3 px-2 py-2">
            <Bone className="size-9 shrink-0 rounded-full" />
            <div className="flex-1 space-y-2">
              <Bone className="h-4 w-3/4" />
              <Bone className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </Card>
      <Card className="hidden space-y-4 lg:block">
        <div className="flex items-center gap-3">
          <Bone className="size-12 rounded-full" />
          <div className="flex-1 space-y-2">
            <Bone className="h-6 w-1/2" />
            <Bone className="h-4 w-2/3" />
          </div>
        </div>
        <div className="divide-y">
          {repeat(5, (i) => (
            <Row key={i} lead="box" />
          ))}
        </div>
      </Card>
    </div>
  ),

  // WeeklyPlanTab: the week's actions, then the seven days.
  plan: () => (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <Bone className="h-9 w-36" />
        <Bone className="h-9 w-40" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 week:grid-cols-7">
        {repeat(7, (i) => (
          <Card key={i} className="h-40 space-y-4 p-4">
            <Bone className="h-3 w-16" />
            <Bone className="h-10 w-full" />
            <Bone className="h-3 w-20" />
          </Card>
        ))}
      </div>
    </div>
  ),

  // GroceryTab: progress, then the list beside adding and the basket.
  groceries: () => (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-4">
        <div className="w-full max-w-md space-y-3">
          <Bone className="h-7 w-48" />
          <Bone className="h-2 w-full rounded-full" />
        </div>
        <div className="flex gap-2">
          <Bone className="h-9 w-28" />
          <Bone className="h-9 w-28" />
        </div>
      </Card>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,44rem)_minmax(0,26rem)]">
        <Card className="divide-y py-2">
          {repeat(8, (i) => (
            <Row key={i} lead="box" />
          ))}
        </Card>
        <Card className="space-y-3">
          <Bone className="h-4 w-40" />
          <Bone className="h-9 w-full" />
        </Card>
      </div>
    </div>
  ),

  account: () => (
    <Card className="max-w-2xl space-y-4">
      <Bone className="h-5 w-40" />
      <Bone className="h-4 w-2/3" />
      <Bone className="h-9 w-36" />
    </Card>
  ),
};
