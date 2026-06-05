"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "dark" | "light";
const THEME_KEY = "roastgpt-theme";
const ThemeCtx = createContext<{
  theme: Theme;
  toggle: () => void;
  set: (t: Theme) => void;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Default to dark. We honor the saved preference on the client; the
  // server-rendered HTML is always the dark theme so there's no flash
  // of unstyled content.
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (typeof window !== "undefined" &&
      window.localStorage.getItem(THEME_KEY)) as Theme | null;
    const initial: Theme = stored === "light" || stored === "dark" ? stored : "dark";
    setTheme(initial);
    document.documentElement.classList.toggle("light", initial === "light");
  }, []);

  const set = (t: Theme) => {
    setTheme(t);
    try {
      window.localStorage.setItem(THEME_KEY, t);
    } catch {
      // localStorage may be disabled (private mode, quota); ignore.
    }
    document.documentElement.classList.toggle("light", t === "light");
  };

  const toggle = () => set(theme === "dark" ? "light" : "dark");

  return <ThemeCtx.Provider value={{ theme, toggle, set }}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export default ThemeProvider;
