import type { KeyboardEvent } from "react";

/**
 * An accessible tab bar.
 *
 * Styled buttons alone tell a screen reader nothing about the relationship
 * between a tab and its panel, so this implements the WAI-ARIA tabs pattern:
 * roles wiring each tab to its panel, and arrow-key navigation with a single
 * tab stop, which is what keyboard users expect from a tab bar.
 */
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
}) {
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const offset =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (offset === 0) return;

    event.preventDefault();
    const next = tabs[(tabs.indexOf(active) + offset + tabs.length) % tabs.length];
    onChange(next);
    document.getElementById(tabId(next))?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="mt-6 flex gap-6 border-b border-edge"
    >
      {tabs.map((tab) => {
        const selected = tab === active;
        return (
          <button
            key={tab}
            id={tabId(tab)}
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(tab)}
            // Only the active tab is in the tab order; arrows move between
            // them. Without this a keyboard user tabs through every one.
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={onKeyDown}
            className={`-mb-px border-b-2 pb-3 text-sm font-semibold transition ${
              selected
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tab}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel<T extends string>({
  tab,
  children,
}: {
  tab: T;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={panelId(tab)}
      aria-labelledby={tabId(tab)}
      tabIndex={0}
      className="pt-8"
    >
      {children}
    </div>
  );
}

const slug = (tab: string) => tab.toLowerCase().replace(/\s+/g, "-");
const tabId = (tab: string) => `tab-${slug(tab)}`;
const panelId = (tab: string) => `panel-${slug(tab)}`;
