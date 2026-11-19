import { ArrowDown, ArrowUp } from "lucide-react";
import { useState } from "react";

import type { Category } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { aisleLabel, DEFAULT_AISLE_ORDER } from "@/lib/aisles";

/**
 * Put the aisles in the order of the person's own shop. Up and down
 * buttons rather than dragging: they work the same by touch, mouse and
 * keyboard, and six rows need no more. Nothing is saved until Save.
 */
export function AisleOrderDialog({
  open,
  onOpenChange,
  order,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  order: readonly Category[];
  onSave: (order: Category[]) => void;
}) {
  const [draft, setDraft] = useState<Category[]>([...order]);

  const move = (index: number, by: -1 | 1) => {
    const next = [...draft];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setDraft(next);
  };
  const isDefault = draft.every((category, i) => category === DEFAULT_AISLE_ORDER[i]);
  const unchanged = draft.every((category, i) => category === order[i]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Opening starts from what is saved, not from a draft left behind.
        if (next) setDraft([...order]);
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <div className="grid gap-1.5 pr-6">
          <DialogTitle>Aisle order</DialogTitle>
          <DialogDescription>
            Put the aisles in the order you walk your shop. Every week's list follows it.
          </DialogDescription>
        </div>

        <ol className="divide-y rounded-lg border">
          {draft.map((category, index) => {
            const label = aisleLabel(category);
            return (
              <li key={category} className="flex items-center gap-2 py-1 pr-1 pl-3">
                <span className="w-5 text-sm text-muted-foreground tabular-nums">{index + 1}</span>
                <span className="flex-1 text-sm">{label}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Move ${label} up`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Move ${label} down`}
                  disabled={index === draft.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown aria-hidden />
                </Button>
              </li>
            );
          })}
        </ol>
        <p className="-mt-2 text-xs text-muted-foreground">
          Anything the app can't place goes under Other, at the end.
        </p>

        <div className="flex flex-wrap justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            disabled={isDefault}
            onClick={() => setDraft([...DEFAULT_AISLE_ORDER])}
          >
            Back to the usual order
          </Button>
          <Button
            type="button"
            disabled={unchanged}
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            Save
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
