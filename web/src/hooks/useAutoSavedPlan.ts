import { useCallback, useEffect, useRef, useState } from "react";

import { DAYS, type Day, type DayAssignment, type Meal, type WeekPlan } from "@/api/types";

export type Draft = Record<Day, DayAssignment>;

export interface Change {
  /** The week as it was before, which Undo puts back. */
  before: Draft;
  /** What changed, for the Undo button: "Tacos on Tuesday". */
  label: string;
}

export type SaveStatus = "saved" | "saving" | "failed";

type Save = (weekStart: string, days: DayAssignment[]) => Promise<WeekPlan | null>;

/**
 * A week's plan that saves itself.
 *
 * Every change is shown at once and sent at once; there is no Save button
 * to forget. Changes made while a save is in flight are merged into one
 * follow-up save of the latest state, so a burst of clicks costs two
 * requests, not one per click, and requests can never land out of order.
 * Each save names its own week, so changing week mid-save cannot file a
 * plan under the wrong one.
 *
 * The last change can be undone (Undo saves the week as it was before). If
 * a save fails, the week goes back to what the server has.
 */
export function useAutoSavedPlan({
  weekStart,
  plan,
  save,
}: {
  weekStart: string;
  plan: readonly DayAssignment[];
  save: Save;
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(plan));
  const [change, setChange] = useState<Change | null>(null);
  const [status, setStatus] = useState<SaveStatus>("saved");

  // Follow the server: a new week, a copy, another tab's change arriving.
  // Not while saving, though, when the draft is newer than anything the
  // server has sent back yet. Adjusted during render rather than in an
  // effect, so a stale week never reaches the screen.
  const [seeded, setSeeded] = useState({ plan, weekStart });
  if (seeded.plan !== plan || seeded.weekStart !== weekStart) {
    const newWeek = seeded.weekStart !== weekStart;
    setSeeded({ plan, weekStart });
    if (newWeek || status !== "saving") setDraft(toDraft(plan));
    if (newWeek) setChange(null);
  }

  const queued = useRef<{ weekStart: string; days: DayAssignment[] } | null>(null);
  const running = useRef(false);
  const latestPlan = useRef(plan);
  useEffect(() => {
    latestPlan.current = plan;
  }, [plan]);

  const flush = useCallback(async () => {
    if (running.current) return; // the loop below will pick it up
    running.current = true;
    setStatus("saving");
    let ok = true;
    while (queued.current) {
      const job = queued.current;
      queued.current = null;
      if (!(await save(job.weekStart, job.days))) {
        ok = false;
        queued.current = null;
        break;
      }
    }
    running.current = false;
    setStatus(ok ? "saved" : "failed");
    if (!ok) {
      // Show what is really saved, not an edit that never arrived.
      setDraft(toDraft(latestPlan.current));
      setChange(null);
    }
  }, [save]);

  /** Show a new version of the week and save it. */
  const apply = (next: Draft, label: string | null) => {
    if (label) setChange({ before: draft, label });
    setDraft(next);
    queued.current = { weekStart, days: DAYS.map((day) => next[day]) };
    void flush();
  };

  const setDay = (day: Day, assignment: Omit<DayAssignment, "day">, label: string) =>
    apply({ ...draft, [day]: { day, ...assignment } }, label);

  return {
    draft,
    status,
    change,
    setDay,
    /** Plan a meal on a day. */
    pick: (day: Day, meal: Meal) =>
      setDay(
        day,
        // A day keeps the servings it had; a new day starts at the recipe's.
        { meal_id: meal.id, servings: draft[day].servings ?? meal.servings },
        `${meal.name} on ${day}`,
      ),
    undo: () => {
      if (!change) return;
      apply(change.before, null);
      setChange(null);
    },
    /** Plan several meals at once, as one change: one Undo puts back all
     *  of them. Each day starts at its recipe's servings. */
    pickMany: (picks: readonly { day: Day; meal: Meal }[], label: string) => {
      if (picks.length === 0) return;
      const next = { ...draft };
      for (const { day, meal } of picks) {
        next[day] = { day, meal_id: meal.id, servings: meal.servings };
      }
      apply(next, label);
    },
    /** Remember the week before a change made elsewhere (a copy), for Undo. */
    remember: (before: Draft, label: string) => setChange({ before, label }),
  };
}

export function toDraft(plan: readonly DayAssignment[]): Draft {
  const byDay = new Map(plan.map((p) => [p.day, p]));
  return Object.fromEntries(
    DAYS.map((day) => [day, byDay.get(day) ?? { day, meal_id: null, servings: null }]),
  ) as Draft;
}
