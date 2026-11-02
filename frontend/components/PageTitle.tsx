"use client";

/**
 * Sets the browser tab to this page's title, in the language the reader is in.
 *
 * `metadata` in a static export is baked at build time, so it can only ever be one
 * language — Spanish, which is what the HTML declares and what a crawler reads. That is
 * correct for crawlers and wrong for a visitor who switched to English and kept a Spanish
 * tab. This closes that gap, and only that gap: the meta description stays static, because
 * the crawlers it is written for do not run this.
 *
 * **Why an observer and not a plain assignment.** Next applies its own metadata title
 * *after* effects run. Measured on 2026-11-02: the effect fired with `lang === "en"` and
 * wrote the English title, and the tab still read Spanish a second and a half later,
 * because the router had overwritten it in between. Assigning once and trusting it loses
 * that race silently — the symptom is a tab nobody looks at. So the title is re-asserted
 * whenever something else changes it, which is a statement about ownership rather than a
 * guess about timing.
 *
 * The guard on `document.title !== wanted` is what keeps the observer from feeding itself:
 * our own write re-triggers it once, finds nothing to do, and stops.
 *
 * Every page renders one, including the 404. Explicit rather than a default set by
 * `LanguageProvider` and overridden here, which would be two effects racing for the same
 * property.
 */

import { useEffect } from "react";

import { useLang } from "./LanguageProvider";
import { copy } from "@/lib/i18n";
import type { Lang, Localized } from "@/lib/i18n";

function compose(title: Localized, lang: Lang): string {
  const suffix = copy.site.name[lang];
  const page = title[lang];
  // The home page is already named after the site; "AutoValor CO · AutoValor CO" is not a
  // title. Mirrors the `template` in layout.tsx so both paths agree.
  return page === suffix ? copy.site.documentTitle[lang] : `${page} · ${suffix}`;
}

export function PageTitle({ title }: { title: Localized }) {
  const { lang } = useLang();

  useEffect(() => {
    const wanted = compose(title, lang);
    const apply = () => {
      if (document.title !== wanted) document.title = wanted;
    };

    apply();
    // The head rather than the `<title>` node: the router may replace the element itself
    // rather than edit its text, and an observer bound to the old node would miss that.
    const observer = new MutationObserver(apply);
    observer.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [lang, title]);

  return null;
}
