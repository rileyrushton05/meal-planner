import { X } from "lucide-react";

import type { GroceryUsual } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

import { AddItemForm } from "./AddItemForm";

/** The things bought most weeks: look over them, add one, take one off. */
export function UsualsDialog({
  open,
  onOpenChange,
  usuals,
  pending,
  onAdd,
  onRemove,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  usuals: readonly GroceryUsual[];
  pending: boolean;
  /** Resolves true once added. */
  onAdd: (text: string) => Promise<boolean>;
  onRemove: (id: number) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <div className="grid gap-1.5 pr-6">
          <DialogTitle>My usuals</DialogTitle>
          <DialogDescription>
            What you buy most weeks. One click puts them all on a week's list.
          </DialogDescription>
        </div>

        {usuals.length > 0 ? (
          <ul className="max-h-72 divide-y overflow-y-auto rounded-lg border">
            {usuals.map((usual) => (
              <li key={usual.id} className="flex items-center gap-2 py-1 pr-1 pl-3">
                <span className="min-w-0 flex-1 truncate text-sm">{usual.name}</span>
                <span className="text-sm text-muted-foreground tabular-nums">{usual.display}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${usual.name} from your usuals`}
                  disabled={pending}
                  onClick={() => onRemove(usual.id)}
                >
                  <X aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
            None yet. Add one here, or keep something from a week's list with its menu.
          </p>
        )}

        <AddItemForm label="Add a usual" pending={pending} onAdd={onAdd} />
      </DialogContent>
    </Dialog>
  );
}
