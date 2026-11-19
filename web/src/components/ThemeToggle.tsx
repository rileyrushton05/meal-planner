import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Theme } from "@/lib/theme";

/**
 * One button in the page header: "Dark theme", pressed or not. It shows the
 * theme you are in, and its tooltip says what a click does.
 */
export function ThemeToggle({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
}) {
  const dark = theme === "dark";
  const Icon = dark ? Moon : Sun;
  return (
    <Button
      variant="outline"
      size="icon"
      aria-label="Dark theme"
      aria-pressed={dark}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => onChange(dark ? "light" : "dark")}
      className="shrink-0"
    >
      <Icon aria-hidden />
    </Button>
  );
}
