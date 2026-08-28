import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { GroceryTab } from "@/components/GroceryTab";
import { MealsTab } from "@/components/meals/MealsTab";
import { WeeklyPlanTab } from "@/components/WeeklyPlanTab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePlanner } from "@/hooks/usePlanner";
import { addDays, formatWeekRange, mondayOf } from "@/lib/dates";

const TABS = [
  { value: "meals", label: "Meals" },
  { value: "plan", label: "Weekly Plan" },
  { value: "grocery", label: "Grocery List" },
] as const;

export default function App() {
  const planner = usePlanner();

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-10 lg:px-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Weekly Meal Planner
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Plan your week, then take the grocery list with you.
          </p>
        </div>
        <WeekPicker
          week={planner.week}
          onChange={planner.setWeek}
          disabled={planner.loading}
        />
      </header>

      {planner.error && (
        <div
          role="alert"
          className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm"
        >
          <span>{planner.error}</span>
          <button
            onClick={planner.dismissError}
            aria-label="Dismiss"
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
      )}

      <Tabs defaultValue="meals">
        <TabsList>
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Only the first load has nothing to show. Later loads keep the
            current week on screen and dim it, so changing week does not blank
            the page. */}
        {!planner.state ? (
          <p role="status" className="py-10 text-sm text-muted-foreground">
            Loading…
          </p>
        ) : (
          <div
            aria-busy={planner.loading}
            className={
              planner.loading ? "opacity-60 transition-opacity" : undefined
            }
          >
            <TabsContent value="meals" className="pt-6">
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
            </TabsContent>

            <TabsContent value="plan" className="pt-6">
              <WeeklyPlanTab
                state={planner.state}
                busy={planner.busy}
                onSave={planner.savePlan}
                onCopyPrevious={planner.copyPreviousWeek}
              />
            </TabsContent>

            <TabsContent value="grocery" className="pt-6">
              <GroceryTab
                weekStart={planner.state.week_start}
                lines={planner.grocery}
                busy={planner.busy}
                onGenerate={planner.generateGroceryList}
              />
            </TabsContent>
          </div>
        )}
      </Tabs>
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
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          disabled={disabled}
          aria-label="Previous week"
          onClick={() => onChange(addDays(week, -7))}
        >
          <ChevronLeft className="size-4" />
        </Button>

        <Input
          type="date"
          value={week}
          disabled={disabled}
          aria-label="Week starting"
          // Any date snaps to its Monday, so the user never has to know which
          // day a week officially starts on.
          onChange={(e) =>
            e.target.value && onChange(mondayOf(new Date(e.target.value)))
          }
          className="w-40"
        />

        <Button
          variant="outline"
          size="icon"
          disabled={disabled}
          aria-label="Next week"
          onClick={() => onChange(addDays(week, 7))}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{formatWeekRange(week)}</p>
    </div>
  );
}
