"use client";

/** Each page's heading and standfirst, translated. Kept apart so the pages themselves can
 * stay server components and read files at build time. */

import { useLang } from "./LanguageProvider";
import { copy } from "@/lib/i18n";

const INTROS = {
  value: { title: copy.hero.title, body: copy.hero.lead },
  market: { title: copy.market.heading, body: copy.market.lead },
  method: { title: copy.method.heading, body: copy.method.lead },
} as const;

export function PageIntro({ page }: { page: keyof typeof INTROS }) {
  const { t } = useLang();
  const intro = INTROS[page];
  return (
    <div className="mb-10 max-w-3xl">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t(intro.title)}</h1>
      <p className="mt-3 text-slate-600 dark:text-slate-400">{t(intro.body)}</p>
    </div>
  );
}
