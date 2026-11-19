import { Check, CopyIcon, LoaderCircle, Sparkles, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { AppState, Day, DayAssignment, Meal, PlanSuggestions, WeekPlan } from "@/api/types";
import { DAYS } from "@/api/types";
import { DayCard } from "@/components/plan/DayCard";
import { Button } from "@/components/ui/button";
import { useAutoSavedPlan } from "@/hooks/useAutoSavedPlan";
import { addDays, fromIso, toIso } from "@/lib/dates";
import { useSearchParam } from "@/lib/location";

/** A day named in the address, or "" for none (or one that is not a day). */
const parseDay = (raw: string | null): Day | "" =>
  DAYS.find((day) => day === raw) ?? "";

interface Props {
  state: AppState;
  pending: boolean;
  onSave: (weekStart: string, days: DayAssignment[]) => Promise<WeekPlan | null>;
  onCopyPrevious: (weekStart: string) => Promise<WeekPlan | null>;
  /** Resolve with the new meal, or null if it could not be made. */
  onCreateMeal: (name: string, servings: number) => Promise<Meal | null>;
  /** Meals for the empty days, or null if that failed. Saves nothing. */
  onSuggest: (weekStart: string, empty: Day[], planned: number[]) => Promise<PlanSuggestions | null>;
}

/**
 * The week, a card per day. Click a day, type a few letters, Enter: the
 * meal is planned and saved. Every change can be undone.
 */
export function WeeklyPlanTab({
  state,
  pending,
  onSave,
  onCopyPrevious,
  onCreateMeal,
  onSuggest,
}: Props) {
  const week = state.week_start;
  const plan = useAutoSavedPlan({ weekStart: week, plan: state.plan, save: onSave });
  const mealsById = new Map(state.meals.map((m) => [m.id, m]));
  const plannedIds = new Set(
    DAYS.map((day) => plan.draft[day].meal_id).filter((id): id is number => id !== null),
  );
  const filled = DAYS.filter((day) => plan.draft[day].meal_id !== null).length;
  const empty = DAYS.filter((day) => plan.draft[day].meal_id === null);
  // Something left to suggest: a meal not already on this week.
  const canFill = empty.length > 0 && state.meals.some((m) => !plannedIds.has(m.id));
  // Said once after filling, when there were not enough meals for every day.
  const [fillNote, setFillNote] = useState<{ week: string; text: string } | null>(null);

  const fillEmptyDays = async () => {
    setFillNote(null);
    const suggested = await onSuggest(week, empty, [...plannedIds]);
    // The week may have changed while asking; these are for the old one.
    if (!suggested || suggested.week_start !== week) return;
    const picks = suggested.days.flatMap(({ day, meal_id }) => {
      const meal = meal_id === null ? undefined : mealsById.get(meal_id);
      return meal && plan.draft[day].meal_id === null ? [{ day, meal }] : [];
    });
    plan.pickMany(picks, `filling ${picks.length} empty ${picks.length === 1 ? "day" : "days"}`);
    if (picks.length < empty.length) {
      setFillNote({
        week,
        text:
          `Filled ${picks.length} of ${empty.length} empty days: every other meal is ` +
          "already on this week. Add more meals for more variety.",
      });
    }
  };
  const todayIso = toIso(new Date());

  // A link can name a day to open on ("/plan?day=Tuesday", from the home
  // page's week). Its search opens once, on arrival, and the day leaves the
  // address, so a refresh or the back button does not open it again.
  const [linkedDay, setLinkedDay] = useSearchParam("day", parseDay);
  const [openOnArrival] = useState(linkedDay);
  useEffect(() => {
    if (linkedDay) setLinkedDay("");
  }, [linkedDay, setLinkedDay]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <p>
            <span className="font-semibold tabular-nums">{filled}</span>
            <span className="text-muted-foreground"> of 7 nights planned</span>
          </p>
          <SaveState status={plan.status} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {plan.change && (
            <Button variant="ghost" onClick={plan.undo} aria-label={`Undo ${plan.change.label}`}>
              <Undo2 aria-hidden />
              Undo
            </Button>
          )}
          <Button
            variant="outline"
            disabled={pending || plan.status === "saving"}
            onClick={async () => {
              const before = plan.draft;
              if (await onCopyPrevious(week)) plan.remember(before, "copying last week");
            }}
          >
            <CopyIcon aria-hidden />
            Copy last week
          </Button>
          {canFill && (
            <Button
              variant="outline"
              disabled={pending || plan.status === "saving"}
              onClick={fillEmptyDays}
              title="Plans the meals you haven't cooked for longest. Undo puts the days back."
            >
              <Sparkles aria-hidden />
              Fill {empty.length === 1 ? "the empty day" : `${empty.length} empty days`}
            </Button>
          )}
        </div>
      </div>

      {fillNote?.week === week && (
        <p role="status" className="text-sm text-muted-foreground">
          {fillNote.text}
        </p>
      )}

      {/* Seven across once each day has room for a meal's name and its
          servings (below that a card overflows), so the week reads as a
          week; four, then two, then one as the screen narrows. */}
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 week:grid-cols-7">
        {DAYS.map((day, index) => {
          const assignment = plan.draft[day];
          const date = addDays(week, index);
          return (
            <DayCard
              key={day}
              day={day}
              date={fromIso(date).getDate()}
              today={date === todayIso}
              assignment={assignment}
              meal={assignment.meal_id === null ? null : (mealsById.get(assignment.meal_id) ?? null)}
              meals={state.meals}
              plannedIds={plannedIds}
              openOnArrival={openOnArrival === day}
              onPick={(meal) => plan.pick(day, meal)}
              onCreate={async (name) => {
                const meal = await onCreateMeal(name, 4);
                if (meal) plan.pick(day, meal);
              }}
              onServings={(servings) =>
                plan.setDay(
                  day,
                  { meal_id: assignment.meal_id, servings },
                  `${servings} servings on ${day}`,
                )
              }
              onClear={() =>
                plan.setDay(day, { meal_id: null, servings: null }, `clearing ${day}`)
              }
            />
          );
        })}
      </ol>
    </div>
  );
}

function SaveState({ status }: { status: "saved" | "saving" | "failed" }) {
  return (
    <p role="status" className="flex items-center gap-1.5 text-muted-foreground">
      {status === "saving" ? (
        <>
          <LoaderCircle aria-hidden className="size-3.5 animate-spin" />
          Saving…
        </>
      ) : status === "failed" ? (
        <>
          <TriangleAlert aria-hidden className="size-3.5 text-destructive" />
          Not saved
        </>
      ) : (
        <>
          <Check aria-hidden className="size-3.5 text-primary" />
          Saved
        </>
      )}
    </p>
  );
}
