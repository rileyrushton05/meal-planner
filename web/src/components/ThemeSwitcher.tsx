import { Moon, Sun } from "lucide-react";

import type { Theme } from "@/lib/theme";

const OPTIONS = [
  { value: "light", label: "Light theme", Icon: Sun },
  { value: "dark", label: "Dark theme", Icon: Moon },
] as const satisfies readonly { value: Theme; label: string; Icon: unknown }[];

/** Two toggle buttons, the current one pressed. */
export function ThemeSwitcher({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Theme"
      className="inline-flex gap-0.5 rounded-lg border bg-card p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          aria-label={label}
          aria-pressed={theme === value}
          title={label}
          onClick={() => onChange(value)}
          className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-pressed:bg-primary-subtle aria-pressed:text-primary-subtle-foreground"
        >
          <Icon className="size-4" aria-hidden />
        </button>
      ))}
    </div>
  );
}
