import { useEffect, useState } from "react";

import type { AppState, Day, DayAssignment } from "../api/types";
import { DAYS } from "../api/types";
import { formatDate } from "../lib/dates";
import { Button, Card, Empty, Field, NumberInput, SectionTitle, Select } from "./ui";

const DAY_COLOR: Record<Day, string> = {
  Monday: "bg-mon",
  Tuesday: "bg-tue",
  Wednesday: "bg-wed",
  Thursday: "bg-thu",
  Friday: "bg-fri",
  Saturday: "bg-sat",
  Sunday: "bg-sun",
};

const UNSET = "";

interface Props {
  state: AppState;
  busy: boolean;
  onSave: (days: DayAssignment[]) => void;
  onCopyPrevious: () => void;
}

export function WeeklyPlanTab({ state, busy, onSave, onCopyPrevious }: Props) {
  // Draft lives in the browser: changing a dropdown is instant and nothing
  // reaches the network until Save.
  const [draft, setDraft] = useState<Record<Day, DayAssignment>>(() =>
    buildDraft(state),
  );

  // Re-seed when the week changes or a save/copy returns new server state.
  useEffect(() => setDraft(buildDraft(state)), [state.week_start, state.plan]);

  const mealsById = new Map(state.meals.map((m) => [m.id, m]));

  const update = (day: Day, patch: Partial<DayAssignment>) =>
    setDraft((current) => ({ ...current, [day]: { ...current[day], ...patch } }));

  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <SectionTitle>Assign Meals to Days</SectionTitle>
          <Button variant="secondary" disabled={busy} onClick={onCopyPrevious}>
            Copy previous week
          </Button>
        </div>

        {state.meals.length === 0 ? (
          <Empty>Add a meal first before assigning it to days.</Empty>
        ) : (
          <Card className="flex flex-col gap-3">
            {DAYS.map((day) => {
              const assignment = draft[day];
              const mealId = assignment.meal_id;
              return (
                <div key={day} className="flex flex-wrap items-end gap-3">
                  <Field label={day}>
                    <Select
                      value={mealId ?? UNSET}
                      onChange={(e) => {
                        const value = e.target.value;
                        const nextId = value === UNSET ? null : Number(value);
                        update(day, {
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
                      <option value={UNSET}>— Unset —</option>
                      {state.meals.map((meal) => (
                        <option key={meal.id} value={meal.id}>
                          {meal.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <div className="w-28">
                    <Field label="Servings">
                      <NumberInput
                        min={1}
                        disabled={mealId === null}
                        value={assignment.servings ?? ""}
                        onChange={(e) =>
                          update(day, {
                            servings: Math.max(1, +e.target.value),
                          })
                        }
                      />
                    </Field>
                  </div>
                </div>
              );
            })}

            <div>
              <Button disabled={busy} onClick={() => onSave(Object.values(draft))}>
                Set Weekly Plan
              </Button>
            </div>
          </Card>
        )}
      </section>

      <section>
        <SectionTitle>Week of {formatDate(state.week_start)}</SectionTitle>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {DAYS.map((day) => {
            const assignment = state.plan.find((p) => p.day === day);
            const meal = assignment?.meal_id
              ? mealsById.get(assignment.meal_id)
              : undefined;
            return (
              <div
                key={day}
                className={`rounded-xl p-3 text-center text-white ${DAY_COLOR[day]}`}
              >
                <p className="text-[0.65rem] font-bold tracking-widest uppercase opacity-85">
                  {day.slice(0, 3)}
                </p>
                <p className="mt-1 font-semibold">{meal?.name ?? "—"}</p>
                {meal && assignment?.servings ? (
                  <p className="text-[0.65rem] tracking-wide uppercase opacity-85">
                    {assignment.servings} serving
                    {assignment.servings === 1 ? "" : "s"}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>
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
