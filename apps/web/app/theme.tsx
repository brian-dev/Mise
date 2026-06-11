"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export const THEMES = ["warm", "fresh", "dark"] as const;
export type Theme = (typeof THEMES)[number];
export const THEME_LABELS: Record<Theme, string> = {
  warm: "Warm Editorial",
  fresh: "Modern Fresh",
  dark: "Dark Premium",
};

const KEY = "mise-theme";
const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: "warm",
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("warm");

  useEffect(() => {
    const saved = localStorage.getItem(KEY) as Theme | null;
    if (saved && THEMES.includes(saved)) setThemeState(saved);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = (t: Theme) => {
    localStorage.setItem(KEY, t);
    setThemeState(t);
  };

  return <Ctx.Provider value={{ theme, setTheme }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
