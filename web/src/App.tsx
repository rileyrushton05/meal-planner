import { useState } from "react";

import { GroceryTab } from "./components/GroceryTab";
import { TabPanel, Tabs } from "./components/Tabs";
import { MealsTab } from "./components/MealsTab";
import { WeeklyPlanTab } from "./components/WeeklyPlanTab";
import { usePlanner } from "./hooks/usePlanner";
import { addDays, formatWeekRange, mondayOf } from "./lib/dates";

const TABS = ["Meals", "Weekly Plan", "Grocery List"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const planner = usePlanner();
  const [tab, setTab] = useState<Tab>("Meals");

  return (
    <div className="mx-auto max-w-5xl px-5 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">
          Weekly Meal Planner
        </h1>
        <p className="mt-1 text-sm text-muted">
          Plan your meals, build your week, and generate your grocery list — all
          in one place.
        </p>
      </header>

      <WeekPicker
        week={planner.week}
        onChange={planner.setWeek}
        disabled={planner.loading}
      />

      {planner.error && (
        <div
          role="alert"
          className="mt-4 flex items-start justify-between gap-3 rounded-xl border border-fri/40 bg-fri/10 px-4 py-3 text-sm"
        >
          <span>{planner.error}</span>
          <button
            onClick={planner.dismissError}
            className="shrink-0 text-muted hover:text-ink"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      <Tabs
        tabs={TABS}
        active={tab}
        onChange={setTab}
        label="Planner sections"
      />

      <main>
        <TabPanel tab={tab}>
          {planner.loading || !planner.state ? (
            <p role="status" className="text-sm text-muted">
              Loading…
            </p>
          ) : tab === "Meals" ? (
            <MealsTab
              state={planner.state}
              busy={planner.busy}
              onAddMeal={planner.addMeal}
              onAddFromTemplate={planner.addFromTemplate}
              onUpdateMeal={planner.updateMeal}
              onDeleteMeal={planner.deleteMeal}
              onAddIngredient={planner.addIngredient}
              onUpdateIngredient={planner.updateIngredient}
              onRemoveIngredient={planner.removeIngredient}
            />
          ) : tab === "Weekly Plan" ? (
            <WeeklyPlanTab
              state={planner.state}
              busy={planner.busy}
              onSave={planner.savePlan}
              onCopyPrevious={planner.copyPreviousWeek}
            />
          ) : (
            <GroceryTab
              weekStart={planner.state.week_start}
              lines={planner.grocery}
              busy={planner.busy}
              onGenerate={planner.generateGroceryList}
            />
          )}
        </TabPanel>
      </main>
    </div>
  );
}

function WeekPicker({
  week,
  onChange,
  disabled,
}: {
  week: string;
  onChange: (week: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        onClick={() => onChange(addDays(week, -7))}
        disabled={disabled}
        className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-muted hover:text-ink disabled:opacity-50"
      >
        ← Previous
      </button>

      <input
        type="date"
        value={week}
        disabled={disabled}
        aria-label="Week starting"
        // Any date snaps to its Monday, so the user never has to know which
        // day a week officially starts on.
        onChange={(e) =>
          e.target.value && onChange(mondayOf(new Date(e.target.value)))
        }
        className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink"
      />

      <button
        onClick={() => onChange(addDays(week, 7))}
        disabled={disabled}
        className="rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-muted hover:text-ink disabled:opacity-50"
      >
        Next →
      </button>

      <span className="text-sm text-muted">{formatWeekRange(week)}</span>
    </div>
  );
}
