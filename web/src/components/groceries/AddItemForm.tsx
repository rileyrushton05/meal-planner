import { Plus } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Longest item the server accepts (schemas.MAX_LINE_LENGTH). */
const MAX_LENGTH = 200;

/**
 * One line to type something to buy, as it would be said: "2 L milk",
 * "bin bags". The server reads the amount, as it does a recipe's lines.
 * What was typed stays if adding fails, to fix; it clears once added.
 */
export function AddItemForm({
  label,
  pending,
  onAdd,
}: {
  label: string;
  pending: boolean;
  /** Resolves true once added. */
  onAdd: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const id = useId();
  const item = text.trim();

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!item) return;
        if (await onAdd(item)) setText("");
      }}
    >
      <div className="min-w-0 flex-1 space-y-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Input
          id={id}
          value={text}
          maxLength={MAX_LENGTH}
          autoComplete="off"
          placeholder="Like 2 L milk, or bin bags"
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <Button type="submit" variant="outline" disabled={pending || !item}>
        <Plus aria-hidden />
        Add
      </Button>
    </form>
  );
}
