import type { AppState, Day, DayAssignment, GroceryLine, Meal, WeekPlan } from "@/api/types";
import { DAYS } from "@/api/types";
import { useAutoSavedPlan } from "@/hooks/useAutoSavedPlan";
import { addDays, fromIso } from "@/lib/dates";

import { TonightCard } from "./TonightCard";
import { WeekStats } from "./WeekStats";
import { WeekStrip } from "./WeekStrip";

interface Props {
  state: AppState;
  /** Today, as an ISO date. */
  today: string;
  /** The week's grocery list, or null while it loads. */
  groceries: readonly GroceryLine[] | null;
  onSave: (weekStart: string, days: DayAssignment[]) => Promise<WeekPlan | null>;
  onCreateMeal: (name: string, servings: number) => Promise<Meal | null>;
}

/**
 * Home: the answer to "what's for dinner?", then how the week is going and
 * what is left to do, each a click from doing it.
 *
 * In this week the focal day is today. In any other week, which is planned
 * ahead or looked back on rather than cooked from, it is the Monday.
 */
export function ThisWeekPage({ state, today, groceries, onSave, onCreateMeal }: Props) {
  const plan = useAutoSavedPlan({ weekStart: state.week_start, plan: state.plan, save: onSave });
  const mealsById = new Map(state.meals.map((m) => [m.id, m]));
  const mealOn = (day: Day) => {
    const id = plan.draft[day].meal_id;
    return id === null ? null : (mealsById.get(id) ?? null);
  };
  const servingsOn = (day: Day) =>
    plan.draft[day].servings ?? mealOn(day)?.servings ?? 0;

  const dates = DAYS.map((_, index) => addDays(state.week_start, index));
  const todayIndex = dates.indexOf(today);
  const focus = Math.max(todayIndex, 0);
  const day = DAYS[focus];

  const planned = new Set(DAYS.filter((d) => mealOn(d) !== null));
  const plannedIds = new Set([...planned].map((d) => plan.draft[d].meal_id as number));
  const servings = [...planned].reduce((total, d) => total + servingsOn(d), 0);

  return (
    <div className="space-y-8">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <TonightCard
          day={day}
          isToday={todayIndex !== -1}
          dateLabel={fromIso(dates[focus]).toLocaleDateString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
          })}
          meal={mealOn(day)}
          servings={servingsOn(day)}
          tomorrow={
            focus < DAYS.length - 1
              ? { day: DAYS[focus + 1], meal: mealOn(DAYS[focus + 1]) }
              : null
          }
          meals={state.meals}
          plannedIds={plannedIds}
          onPick={(meal) => plan.pick(day, meal)}
          onCreate={async (name) => {
            const meal = await onCreateMeal(name, 4);
            if (meal) plan.pick(day, meal);
          }}
        />
        <WeekStats
          plannedDays={planned}
          servings={servings}
          mealCount={plannedIds.size}
          // Still to get: not yet in the basket, and not already at home.
          itemsToBuy={groceries ? groceries.filter((line) => line.state === null).length : null}
        />
      </div>

      <WeekStrip
        days={DAYS.map((d, index) => ({
          day: d,
          date: fromIso(dates[index]).getDate(),
          today: index === todayIndex,
          meal: mealOn(d),
        }))}
      />
    </div>
  );
}
