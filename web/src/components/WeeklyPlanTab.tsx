import { CopyIcon } from "lucide-react";
import { useState } from "react";

import type { AppState, Day, DayAssignment, Meal } from "@/api/types";
import { DAYS } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatDate } from "@/lib/dates";

/** A hue per day, so a filled week reads at a glance. */
const DAY_ACCENT: Record<Day, string> = {
  Monday: "bg-mon",
  Tuesday: "bg-tue",
  Wednesday: "bg-wed",
  Thursday: "bg-thu",
  Friday: "bg-fri",
  Saturday: "bg-sat",
  Sunday: "bg-sun",
};

const UNSET = "unset";

interface Props {
  state: AppState;
  busy: boolean;
  onSave: (days: DayAssignment[]) => void;
  onCopyPrevious: () => void;
}

export function WeeklyPlanTab({ state, busy, onSave, onCopyPrevious }: Props) {
  // The draft lives in the browser: editing a day is instant, and nothing
  // reaches the network until Save.
  const [draft, setDraft] = useState<Record<Day, DayAssignment>>(() =>
    buildDraft(state),
  );

  // Re-seed when the server plan changes. Adjusting state during render
  // rather than in an effect, so a stale draft never reaches the DOM.
  const [seededFrom, setSeededFrom] = useState(state.plan);
  if (seededFrom !== state.plan) {
    setSeededFrom(state.plan);
    setDraft(buildDraft(state));
  }

  const mealsById = new Map(state.meals.map((m) => [m.id, m]));
  const dirty = DAYS.some((day) => !sameAssignment(draft[day], state.plan, day));

  const update = (day: Day, patch: Partial<DayAssignment>) =>
    setDraft((current) => ({ ...current, [day]: { ...current[day], ...patch } }));

  if (state.meals.length === 0) {
    return (
      <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
        Add a meal first, then you can plan your week.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            Week of {formatDate(state.week_start)}
          </h2>
          <p className="text-sm text-muted-foreground">
            Pick a meal for each day, then save.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={busy} onClick={onCopyPrevious}>
            <CopyIcon className="size-4" />
            Copy previous week
          </Button>
          <Button
            disabled={busy || !dirty}
            onClick={() => onSave(Object.values(draft))}
          >
            Save plan
          </Button>
        </div>
      </div>

      {/* Column-flow so the week reads Mon-Thu down the left and Fri-Sun down
          the right, rather than zig-zagging across two columns. */}
      <div className="grid gap-2 xl:grid-flow-col xl:grid-cols-2 xl:grid-rows-4">
        {DAYS.map((day) => (
          <DayRow
            key={day}
            day={day}
            assignment={draft[day]}
            meals={state.meals}
            mealsById={mealsById}
            onChange={(patch) => update(day, patch)}
          />
        ))}
      </div>
    </div>
  );
}

function DayRow({
  day,
  assignment,
  meals,
  mealsById,
  onChange,
}: {
  day: Day;
  assignment: DayAssignment;
  meals: Meal[];
  mealsById: Map<number, Meal>;
  onChange: (patch: Partial<DayAssignment>) => void;
}) {
  const mealId = assignment.meal_id;
  const assigned = mealId !== null;

  return (
    <div
      className={`flex items-stretch gap-3 overflow-hidden rounded-xl border bg-card p-3 transition-colors ${
        assigned ? "border-border" : "border-dashed bg-card/40"
      }`}
    >
      <span
        aria-hidden
        className={`w-1 shrink-0 rounded-full ${
          assigned ? DAY_ACCENT[day] : "bg-border"
        }`}
      />

      {/* Wraps rather than squeezing the meal name: on a narrow screen the
          servings field drops to a second line instead. */}
      <div className="flex flex-1 flex-wrap items-center gap-x-3 gap-y-2">
        <p
          className={`w-24 shrink-0 text-sm font-semibold ${
            assigned ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          {day}
        </p>

        <Select
          value={mealId === null ? UNSET : String(mealId)}
          onValueChange={(value) => {
            const nextId = value === UNSET ? null : Number(value);
            onChange({
              meal_id: nextId,
              // Default to the recipe's own serving size.
              servings:
                nextId === null
                  ? null
                  : (assignment.servings ??
                    mealsById.get(nextId)?.servings ??
                    1),
            });
          }}
        >
          <SelectTrigger aria-label={day} className="h-9 min-w-40 flex-1">
            <SelectValue>
              {(value: string) =>
                value === UNSET
                  ? "No meal"
                  : (mealsById.get(Number(value))?.name ?? "No meal")
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={UNSET}>No meal</SelectItem>
            {meals.map((meal) => (
              <SelectItem key={meal.id} value={String(meal.id)}>
                {meal.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {assigned && (
          <div className="flex shrink-0 items-center gap-2">
            <Label
              htmlFor={`servings-${day}`}
              className="text-xs text-muted-foreground"
            >
              Serves
            </Label>
            <Input
              id={`servings-${day}`}
              type="number"
              min={1}
              value={assignment.servings ?? ""}
              onChange={(e) => onChange({ servings: Math.max(1, +e.target.value) })}
              className="h-9 w-16"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function buildDraft(state: AppState): Record<Day, DayAssignment> {
  const byDay = new Map(state.plan.map((p) => [p.day, p]));
  return Object.fromEntries(
    DAYS.map((day) => [
      day,
      byDay.get(day) ?? { day, meal_id: null, servings: null },
    ]),
  ) as Record<Day, DayAssignment>;
}

function sameAssignment(
  draft: DayAssignment,
  plan: DayAssignment[],
  day: Day,
): boolean {
  const saved = plan.find((p) => p.day === day);
  return (
    (saved?.meal_id ?? null) === draft.meal_id &&
    (saved?.servings ?? null) === draft.servings
  );
}
