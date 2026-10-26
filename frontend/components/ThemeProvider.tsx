"use client";

/**
 * Theme state: light, dark, or follow the system.
 *
 * Built on the same `useSyncExternalStore` pattern as `LanguageProvider`, for the same
 * reasons — `localStorage` is an external store, and reading it in an effect would paint
 * once in the wrong theme before correcting itself.
 *
 * **"Auto" is a stored choice, not the absence of one.** It writes `auto` rather than
 * clearing the key, so a visitor who deliberately returns to following their system is
 * remembered as having chosen that. The three states then map onto two mechanisms: `light`
 * and `dark` stamp `data-theme` on `<html>`, and `auto` removes the attribute so the
 * `prefers-color-scheme` block in globals.css takes over.
 *
 * The first paint is handled by an inline script in `<head>`, not here: React runs after
 * the document is parsed, so any React-based fix is a flash by construction.
 */

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

export const THEMES = ["light", "auto", "dark"] as const;
export type Theme = (typeof THEMES)[number];

const STORAGE_KEY = "autovalor.theme";
const DEFAULT_THEME: Theme = "auto";

/**
 * The script that runs before the first paint.
 *
 * Exported as a string so `layout.tsx` can inline it in `<head>` and this module stays the
 * one place that knows the storage key and the attribute. It stays deliberately tiny: it
 * blocks parsing, and anything slower than reading one key would cost more than the flash
 * it prevents. A `try` because Safari in private mode throws on `localStorage`.
 */
export const THEME_SCRIPT = `try{var t=localStorage.getItem(${JSON.stringify(STORAGE_KEY)});if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

const listeners = new Set<() => void>();

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  // Another tab writing the same key.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "auto" || value === "dark";
}

function getSnapshot(): Theme {
  // A string snapshot, so value equality is enough and no cache is needed.
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isTheme(stored) ? stored : DEFAULT_THEME;
}

function getServerSnapshot(): Theme {
  return DEFAULT_THEME;
}

function store(theme: Theme): void {
  window.localStorage.setItem(STORAGE_KEY, theme);
  listeners.forEach((listener) => listener());
}

type ThemeState = { theme: Theme; setTheme: (theme: Theme) => void };

const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") {
      delete root.dataset.theme;
    } else {
      root.dataset.theme = theme;
    }
  }, [theme]);

  const value = useMemo<ThemeState>(() => ({ theme, setTheme: store }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
