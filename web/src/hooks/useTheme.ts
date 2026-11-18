import { useCallback, useEffect, useState } from "react";

import { applyTheme, savedTheme, saveTheme, type Theme } from "@/lib/theme";

/** The chosen theme and a way to change it. */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(savedTheme);

  useEffect(() => applyTheme(theme), [theme]);

  const setTheme = useCallback((next: Theme) => {
    saveTheme(next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
