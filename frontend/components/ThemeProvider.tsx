"use client";

/**
 * Theme state: light, dark, or follow the system.
 *
 * Built on the same `useSyncExternalStore` pattern as `LanguageProvider`, for the same
 * reasons — `localStorage` is an external store, and reading it in an effect would paint
 * once in the wrong theme before correcting itself. The system's colour scheme is a second
 * external store, read the same way.
 *
 * **Two values, not one.** The *preference* is what the visitor chose (`light`, `auto` or
 * `dark`) and it is what the toggle shows; the *resolved* theme is the one the page is
 * actually painted in, and it is only ever `light` or `dark`. `auto` resolves against
 * `prefers-color-scheme` here rather than being handed to CSS, because `data-theme` is what
 * the `dark` variant in globals.css keys off: leaving the attribute off under `auto` set the
 * tokens from the media query but activated no `dark:` utility, so the older components
 * painted their light-mode classes onto a dark page — white cards on near-black. The
 * attribute is the single switch, so it always carries a real value.
 *
 * `data-theme-pref` carries the preference alongside it, so what the visitor chose is
 * readable from the document and not only from React state.
 *
 * The first paint is handled by an inline script in `<head>`, not here: React runs after
 * the document is parsed, so any React-based fix is a flash by construction.
 */

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

export const THEMES = ["light", "auto", "dark"] as const;
export type Theme = (typeof THEMES)[number];
/** What the page is painted in: `auto` has already been resolved away. */
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "autovalor.theme";
const DEFAULT_THEME: Theme = "auto";
const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * The script that runs before the first paint.
 *
 * Exported as a string so `layout.tsx` can inline it in `<head>` and this module stays the
 * one place that knows the storage key and the attributes. It stays deliberately tiny: it
 * blocks parsing, and anything slower than reading one key would cost more than the flash
 * it prevents. It has to resolve `auto` itself — the whole point is that the attribute is
 * correct before anything is painted, and `auto` is the default, so this is the common path
 * and not an edge case. A `try` because Safari in private mode throws on `localStorage`.
 *
 * Only `tests/theme.test.tsx` ever checks this: a string is invisible to both tsc and
 * ESLint, and it has to agree with the provider or the page flashes on every load.
 */
export const THEME_SCRIPT = `try{var d=document.documentElement,p=localStorage.getItem(${JSON.stringify(STORAGE_KEY)});if(p!=="light"&&p!=="dark"&&p!=="auto")p=${JSON.stringify(DEFAULT_THEME)};d.dataset.themePref=p;d.dataset.theme=p==="auto"?(matchMedia(${JSON.stringify(DARK_QUERY)}).matches?"dark":"light"):p}catch(e){}`;

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

/**
 * The system's colour scheme as an external store, so a visitor on `auto` who flips their
 * operating system over sees the page follow without reloading.
 */
function subscribeToSystem(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getSystemScheme(): ResolvedTheme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function getServerSystemScheme(): ResolvedTheme {
  // Dark is the reference theme, so it is the server's guess; the inline script corrects
  // it before the first paint either way.
  return "dark";
}

type ThemeState = { theme: Theme; resolved: ResolvedTheme; setTheme: (theme: Theme) => void };

const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const system = useSyncExternalStore(subscribeToSystem, getSystemScheme, getServerSystemScheme);
  const resolved: ResolvedTheme = theme === "auto" ? system : theme;

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolved;
    root.dataset.themePref = theme;
    // The browser chrome (and the installed app's title bar) follows the chosen theme, not
    // only the system's: the metas carry a media query each, so both get the ground the
    // page is actually painted with, read back from the stylesheet rather than repeated.
    const ground = getComputedStyle(root).getPropertyValue("--ground").trim();
    if (ground) {
      for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
        meta.content = ground;
      }
    }
  }, [resolved, theme]);

  const value = useMemo<ThemeState>(() => ({ theme, resolved, setTheme: store }), [theme, resolved]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
