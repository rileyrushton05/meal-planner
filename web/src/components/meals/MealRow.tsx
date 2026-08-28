import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import type { Meal } from "@/api/types";
import {
  AlertDialog,
  AlertDialogAction,
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

export function MealRow({
  meal,
  busy,
  onUpdate,
  onDelete,
}: {
  meal: Meal;
  busy: boolean;
  onUpdate: (id: number, name: string, servings: number) => void;
  onDelete: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(meal.name);
  const [servings, setServings] = useState(String(meal.servings));

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <p className="truncate font-medium">{meal.name}</p>
          <p className="text-sm text-muted-foreground">
            Serves {meal.servings} · {meal.ingredients.length} ingredient
            {meal.ingredients.length === 1 ? "" : "s"}
          </p>
        </div>

        <div className="flex shrink-0 gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${meal.name}`}
            onClick={() => setEditing(!editing)}
          >
            <Pencil className="size-4" />
          </Button>

          <AlertDialog>
            <AlertDialogTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${meal.name}`}
                />
              }
            >
              <Trash2 className="size-4" />
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete {meal.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  This also removes its ingredients and unassigns it from any
                  planned day.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  disabled={busy}
                  onClick={() => onDelete(meal.id)}
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {editing && (
        <div className="flex flex-wrap items-end gap-3 border-t p-4">
          <div className="min-w-48 flex-1 space-y-2">
            <Label htmlFor={`name-${meal.id}`}>Meal name</Label>
            <Input
              id={`name-${meal.id}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="w-24 space-y-2">
            <Label htmlFor={`servings-${meal.id}`}>Servings</Label>
            <Input
              id={`servings-${meal.id}`}
              type="number"
              min={1}
              value={servings}
              onChange={(e) => setServings(e.target.value)}
            />
          </div>
          <Button
            disabled={busy || !name.trim()}
            onClick={() => {
              onUpdate(meal.id, name.trim(), Math.max(1, Number(servings) || 1));
              setEditing(false);
            }}
          >
            Save
          </Button>
          <Button variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
