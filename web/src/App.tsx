import { CalendarDays, House, ShieldCheck, ShoppingBasket, UserRound, UtensilsCrossed } from "lucide-react";
import { ChevronLeft, ChevronRight, CloudOff, LoaderCircle, RotateCw, X } from "lucide-react";
import { useEffect } from "react";

import { AccountBar } from "@/components/AccountBar";
import { AccountPage } from "@/components/AccountPage";
import { AppShell, type NavPage } from "@/components/AppShell";
import { type GroceryActions, GroceryTab } from "@/components/GroceryTab";
import { ThisWeekPage } from "@/components/home/ThisWeekPage";
import { MealsTab } from "@/components/meals/MealsTab";
import { PageSkeleton, type SkeletonPage } from "@/components/PageSkeleton";
import { PrivacyPage } from "@/components/PrivacyPage";
import { ThemeToggle } from "@/components/ThemeToggle";
import { WeeklyPlanTab } from "@/components/WeeklyPlanTab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAccount } from "@/hooks/useAccount";
import { type Freshness, usePlanner } from "@/hooks/usePlanner";
import { useTheme } from "@/hooks/useTheme";
import { addDays, formatWeekRange, mondayOf, toIso, weekName } from "@/lib/dates";
import { navigate, usePathname } from "@/lib/location";

const APP_NAME = "The Fridge Door";

interface Page extends NavPage {
  id: SkeletonPage | "privacy";
  /** The heading at the top of the page, and the browser tab's title. */
  title: string;
  /** Whether what the page shows depends on the week, so it has a picker. */
  weekly: boolean;
  /** In the main navigation. The account page is reached from the account
   *  controls instead: it is not part of planning a week. */
  nav: boolean;
}

/**
 * Home first, then in the order a week is put together: meals, then the
 * plan, then shopping.
 */
const PAGES: readonly Page[] = [
  { id: "home", path: "/", label: "This week", title: "This week", icon: House, weekly: true, nav: true },
  { id: "meals", path: "/meals", label: "Meals", title: "Meals", icon: UtensilsCrossed, weekly: false, nav: true },
  { id: "plan", path: "/plan", label: "Plan", title: "Weekly plan", icon: CalendarDays, weekly: true, nav: true },
  { id: "groceries", path: "/groceries", label: "Groceries", title: "Groceries", icon: ShoppingBasket, weekly: true, nav: true },
  { id: "account", path: "/account", label: "Account", title: "Account", icon: UserRound, weekly: false, nav: false },
  { id: "privacy", path: "/privacy", label: "Privacy", title: "Privacy", icon: ShieldCheck, weekly: false, nav: false },
];
const NAV_PAGES = PAGES.filter((page) => page.nav);

/** The page at a path; anything unknown goes home. */
function pageAt(path: string): Page {
  return PAGES.find((page) => page.path === path) ?? PAGES[0];
}

export default function App() {
  const page = pageAt(usePathname());
  const planner = usePlanner({
    loadGroceries: page.id === "home" || page.id === "groceries",
  });
  const session = useAccount();
  const theme = useTheme();
  // Home is named for the week it shows: "This week", "Next week"...
  const title = page.id === "home" ? weekName(planner.week) : page.title;

  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);

  return (
    <AppShell
      pages={NAV_PAGES}
      current={page.id}
      footer={
        <AccountBar
          account={session.account}
          onSignUp={session.signUp}
          onLogIn={session.logIn}
          onRecover={session.recover}
          onLogOut={session.logOut}
          loggingOut={session.loggingOut}
        />
      }
    >
      {/* The title and the theme on one line; the week picker between them
          when there is room, and on a line of its own on a phone. */}
      <header className="flex min-h-16 flex-wrap items-center gap-x-3 gap-y-3 border-b px-4 py-3 sm:px-6 lg:px-8">
        <div className="mr-auto flex min-w-0 items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {page.id !== "privacy" && <FreshnessNote freshness={planner.freshness} />}
        </div>
        {page.weekly && (
          <div className="order-last basis-full md:order-none md:basis-auto">
            <WeekPicker
              week={planner.week}
              onChange={planner.setWeek}
              disabled={planner.loading}
            />
          </div>
        )}
        <ThemeToggle theme={theme.theme} onChange={theme.setTheme} />
      </header>

      {/* Aligned with the title above, not centred, and as wide as the
          screen allows up to a limit, so a big monitor gets bigger cards
          rather than wider margins. */}
      <main className="max-w-[1680px] px-4 py-6 sm:px-6 lg:px-8">
        {session.notice && (
          <div
            role="status"
            className="mb-6 flex items-start justify-between gap-3 rounded-lg border bg-card px-4 py-3 text-sm"
          >
            <span>{session.notice}</span>
            <button
              onClick={session.dismissNotice}
              aria-label="Dismiss"
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        {planner.error && (
          <div
            role="alert"
            className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm"
          >
            <span className="min-w-0 flex-1">
              {planner.error}
              {planner.freshness === "offline" &&
                " You're seeing what you had last time; changes are off until it loads."}
            </span>
            {/* With nothing on screen, the panel below offers it instead. */}
            {planner.loadFailed && planner.state && (
              <Button variant="outline" size="sm" className="-my-1" onClick={planner.retry}>
                <RotateCw aria-hidden />
                Try again
              </Button>
            )}
            <button
              onClick={planner.dismissError}
              aria-label="Dismiss"
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        {/* Only the first load has nothing to show, and shows the page's
            outline instead. Later loads keep the current week on screen and
            dim it, so changing week does not blank the page. A visit that
            opens on the last one's data shows it as it is, but inert: it
            can be read, and changed once the real data has replaced it. */}
        {/* Needs nothing from the API, so it shows even when that is down. */}
        {page.id === "privacy" ? (
          <PrivacyPage />
        ) : !planner.state ? (
          planner.loadFailed ? (
            <div className="rounded-xl border border-dashed p-10 text-center">
              <p className="font-heading text-lg font-semibold">Your planner didn't load</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Nothing is lost: your meals and plans are saved on the server.
              </p>
              <Button className="mt-4" onClick={planner.retry}>
                <RotateCw aria-hidden />
                Try again
              </Button>
            </div>
          ) : (
            <PageSkeleton page={page.id} />
          )
        ) : (
          <div
            aria-busy={planner.loading || planner.freshness === "updating"}
            inert={planner.freshness !== "live"}
            className={planner.loading ? "opacity-60 transition-opacity" : undefined}
          >
            {page.id === "home" && (
              <ThisWeekPage
                state={planner.state}
                today={toIso(new Date())}
                groceries={planner.grocery?.lines ?? null}
                onSave={planner.savePlan}
                onCreateMeal={planner.addMeal}
              />
            )}
            {page.id === "account" && session.account && (
              <AccountPage
                account={session.account}
                onReplaceRecoveryCode={session.replaceRecoveryCode}
                onExport={session.exportAccount}
                onDelete={async (password) => {
                  await session.deleteAccount(password);
                  navigate("/");
                }}
              />
            )}
            {page.id === "meals" && (
              <MealsTab
                state={planner.state}
                pending={planner.mealsPending}
                onAddMeal={planner.addMeal}
                onAddFromTemplate={planner.addFromTemplate}
                onDuplicateMeal={planner.duplicateMeal}
                onImportRecipe={planner.importRecipe}
                onUpdateMeal={planner.updateMeal}
                onDeleteMeal={planner.deleteMeal}
                onAddIngredient={planner.addIngredient}
                onUpdateIngredient={planner.updateIngredient}
                onRemoveIngredient={planner.removeIngredient}
                onReadIngredients={planner.readIngredients}
                onReplaceIngredients={planner.replaceIngredients}
              />
            )}
            {page.id === "plan" && (
              <WeeklyPlanTab
                state={planner.state}
                pending={planner.planPending}
                onSave={planner.savePlan}
                onCopyPrevious={planner.copyPreviousWeek}
                onCreateMeal={planner.addMeal}
                onSuggest={planner.suggestMeals}
              />
            )}
            {page.id === "groceries" && (
              <GroceryTab
                weekStart={planner.state.week_start}
                list={planner.grocery}
                plannedDays={planner.state.plan.filter((d) => d.meal_id !== null).length}
                pending={planner.groceryPending}
                {...groceryActions(planner, planner.state.week_start)}
              />
            )}
          </div>
        )}
      </main>
    </AppShell>
  );
}

/**
 * Beside the title while the page shows the last visit's data: that it is
 * being brought up to date, or that it could not be, and so is a copy.
 */
function FreshnessNote({ freshness }: { freshness: Freshness }) {
  if (freshness === "live") return null;
  const updating = freshness === "updating";
  return (
    <span
      role="status"
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-card px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
    >
      {updating ? (
        <LoaderCircle aria-hidden className="size-3.5 motion-safe:animate-spin" />
      ) : (
        <CloudOff aria-hidden className="size-3.5" />
      )}
      {updating ? "Updating…" : "Last visit's copy"}
    </span>
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
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <p className="text-sm text-muted-foreground tabular-nums">{formatWeekRange(week)}</p>
      <div className="flex items-center gap-1.5">
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
          className="w-36"
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
    </div>
  );
}

/** The grocery page's actions, each bound to the week on screen. */
function groceryActions(
  planner: ReturnType<typeof usePlanner>,
  week: string,
): GroceryActions {
  return {
    onCheck: (key, state) => planner.setGroceryCheck(week, key, state),
    onEmptyBasket: () => planner.emptyBasket(week),
    onAddExtra: (text) => planner.addExtra(week, text),
    onRemoveExtra: (id) => planner.removeExtra(week, id),
    onKeepExtra: (id) => planner.keepExtra(week, id),
    onAddUsuals: () => planner.addUsuals(week),
    onAddUsual: planner.addUsual,
    onRemoveUsual: planner.removeUsual,
    onAisleOrder: planner.setAisleOrder,
  };
}
