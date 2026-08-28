import { useState } from "react";

import { Button, Card, Field, NumberInput, SectionTitle, TextInput } from "../ui";

export function AddMealForm({
  onAdd,
  busy,
}: {
  onAdd: (name: string, servings: number) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("");
  // Held as text, not a number. Coercing on every keystroke made the field
  // impossible to clear: it snapped back to 1, so typing "4" gave "14".
  const [servings, setServings] = useState("1");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim(), Math.max(1, Number(servings) || 1));
    setName("");
    setServings("1");
  };

  return (
    <section>
      <SectionTitle>Add a Meal</SectionTitle>
      <Card>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Meal name">
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Spaghetti Bolognese"
            />
          </Field>
          <div className="w-28">
            <Field label="Servings">
              <NumberInput
                min={1}
                value={servings}
                onChange={(e) => setServings(e.target.value)}
              />
            </Field>
          </div>
          <Button type="submit" disabled={busy || !name.trim()}>
            Add Meal
          </Button>
        </form>
      </Card>
    </section>
  );
}
