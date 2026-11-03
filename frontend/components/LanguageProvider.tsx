"use client";

/**
 * Language state for the whole site.
 *
 * A static export has no server, so the language cannot be a route segment without
 * doubling every page in the build, and it cannot be negotiated from a request header
 * either. It lives in the client: Spanish by default, remembered in `localStorage`, and
 * written onto `<html lang>` so assistive technology and the browser's own translation
 * agree with what is on screen.
 *
 * `localStorage` is read through `useSyncExternalStore` rather than in an effect. That is
 * what the API is for — it is an external store — and it buys three things an effect does
 * not: the prerendered HTML is Spanish by construction via the server snapshot, hydration
 * does not flash, and a visitor with two tabs open gets both switched by the `storage`
 * event for free.
 */

import { createContext, useContext, useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import type { Lang, Localized } from "@/lib/i18n";

const STORAGE_KEY = "autovalor.lang";
const DEFAULT_LANG: Lang = "es";

/**
 * Inlined in `<head>`, before the first paint, like the theme script. The export is
 * rendered in Spanish, so a visitor who chose English used to see a frame or more of
 * Spanish before hydration switched it. When English is stored this sets `lang` and holds
 * the body hidden (`data-lang-pending`, see globals.css) until the provider has rendered
 * English; a timer releases it after 3 s if the scripts never run.
 */
export const LANG_SCRIPT = `try{if(localStorage.getItem(${JSON.stringify(STORAGE_KEY)})==="en"){var d=document.documentElement;d.lang="en";d.dataset.langPending="";setTimeout(function(){delete d.dataset.langPending},3000)}}catch(e){}`;

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

function getSnapshot(): Lang {
  // Snapshots must be stable between renders. This one is a string, so value equality is
  // enough and no cache is needed.
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "en" || stored === "es" ? stored : DEFAULT_LANG;
}

function getServerSnapshot(): Lang {
  return DEFAULT_LANG;
}

function store(lang: Lang): void {
  window.localStorage.setItem(STORAGE_KEY, lang);
  listeners.forEach((listener) => listener());
}

type LanguageState = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Resolve a two-language string in the current language. */
  t: (text: Localized) => string;
};

const LanguageContext = createContext<LanguageState | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // A layout effect, so the body is shown in the same frame as the English text and not
  // one after it. The first commit during hydration is the server's Spanish; the hold is
  // only released once the rendered language is the stored one.
  useLayoutEffect(() => {
    // Never write the server's Spanish over what LANG_SCRIPT set: `lang` would flip
    // en -> es -> en during hydration.
    if (lang !== getSnapshot()) return;
    const root = document.documentElement;
    root.lang = lang;
    delete root.dataset.langPending;
  }, [lang]);

  const value = useMemo<LanguageState>(
    () => ({ lang, setLang: store, t: (text: Localized) => text[lang] }),
    [lang],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang(): LanguageState {
  const context = useContext(LanguageContext);
  if (context === null) {
    throw new Error("useLang must be used inside LanguageProvider");
  }
  return context;
}
