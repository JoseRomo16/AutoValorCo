"use client";

/**
 * The heading and standfirst for Market and Methodology.
 *
 * Kept apart from the pages so they can stay server components and read files at build
 * time. The valuation page does not use this: it has its own hero, because it is the one
 * page that opens with a form rather than with a document.
 *
 * The eyebrow names the section and mirrors the active navigation item, which is what makes
 * it orientation rather than ornament. One per page, at the top, and nowhere else.
 */

import { useLang } from "./LanguageProvider";
import { WRAP } from "./SiteChrome";
import { copy } from "@/lib/i18n";

const INTROS = {
  market: { eyebrow: copy.nav.market, title: copy.market.heading, body: copy.market.lead },
  method: { eyebrow: copy.nav.method, title: copy.method.heading, body: copy.method.lead },
} as const;

export function PageIntro({ page }: { page: keyof typeof INTROS }) {
  const { t } = useLang();
  const intro = INTROS[page];
  return (
    <section className={`${WRAP} pb-10 pt-14 sm:pt-20`}>
      <p className="mb-4 font-mono text-sm uppercase tracking-[0.12em] text-accent-text">
        {t(intro.eyebrow)}
      </p>
      <h1 className="max-w-[18ch] font-display text-step-h1 font-extrabold leading-[1.03] tracking-[-0.02em] text-balance [font-stretch:118%]">
        {t(intro.title)}
      </h1>
      <p className="mt-6 max-w-[62ch] text-xl leading-relaxed text-muted">{t(intro.body)}</p>
    </section>
  );
}
