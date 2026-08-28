import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function AddMealForm({
  onAdd,
  busy,
}: {
  onAdd: (name: string, servings: number) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("");
  // Held as text so the field can be cleared; coercing per keystroke made it
  // snap back to 1, so typing "4" gave "14".
  const [servings, setServings] = useState("1");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim(), Math.max(1, Number(servings) || 1));
    setName("");
    setServings("1");
  };

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4"
    >
      <div className="min-w-48 flex-1 space-y-2">
        <Label htmlFor="meal-name">Meal name</Label>
        <Input
          id="meal-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Spaghetti Bolognese"
        />
      </div>
      <div className="w-24 space-y-2">
        <Label htmlFor="meal-servings">Servings</Label>
        <Input
          id="meal-servings"
          type="number"
          min={1}
          value={servings}
          onChange={(e) => setServings(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={busy || !name.trim()}>
        <Plus className="size-4" />
        Add meal
      </Button>
    </form>
  );
}
