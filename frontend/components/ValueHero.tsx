"use client";

/**
 * The opening of the valuation page.
 *
 * The question is the hero, set large enough to be the page's only loud element. Under it
 * go three facts that answer "why should I believe this number", in the order someone would
 * ask them: when the data is from, how much of it there is, and how wrong the model usually
 * is. The error is published for both verticals rather than averaged — one figure covering
 * cars and motorcycles would hide that motorcycles are twice as hard.
 *
 * Every figure arrives as a prop, read from `model.json` at build time. Nothing here is
 * typed by hand.
 */

import { useLang } from "./LanguageProvider";
import { WRAP } from "./SiteChrome";
import { integer, isoDay, percent } from "@/lib/format";
import { copy, fill } from "@/lib/i18n";

export type HeroFacts = {
  listings: number;
  carMape: number;
  motorcycleMape: number;
  lastCapture: string;
};

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-line py-1 sm:border-l sm:pl-6 sm:first:border-l-0 sm:first:pl-0 min-[960px]:flex min-[960px]:items-baseline min-[960px]:gap-2 min-[960px]:pr-6">
      <dt className="whitespace-nowrap text-caption text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-sm tabular-nums min-[960px]:mt-0">{children}</dd>
    </div>
  );
}

export function ValueHero({ facts }: { facts: HeroFacts }) {
  const { lang, t } = useLang();

  return (
    // Compact on desktop, where the form has to reach above the fold: "Calcular el precio"
    // is visible without scrolling at 1440 × 900. The title fits one line there.
    <section className={`${WRAP} pb-10 pt-14 sm:max-[959px]:pt-20 min-[960px]:pb-5 min-[960px]:pt-6`}>
      {/* The one eyebrow on the page. It names the section, mirroring the active nav item,
          so it is orientation rather than decoration. */}
      <p className="mb-4 font-mono text-sm uppercase tracking-[0.12em] text-accent-text min-[960px]:mb-2">
        {t(copy.nav.value)}
      </p>

      <h1 className="max-w-[18ch] font-display text-step-h1 font-extrabold leading-[1.03] tracking-[-0.02em] text-balance [font-stretch:118%] min-[960px]:max-w-none min-[960px]:text-[2.5rem]">
        {t(copy.hero.title)}
      </h1>

      <p className="mt-6 max-w-[62ch] text-xl leading-relaxed text-muted min-[960px]:mt-2 min-[960px]:max-w-[80ch] min-[960px]:text-lg">{t(copy.hero.lead)}</p>

      <dl className="mt-9 grid gap-5 sm:grid-cols-3 sm:gap-0 min-[960px]:mt-3 min-[960px]:flex min-[960px]:flex-wrap min-[960px]:gap-y-1">
        <Fact label={t(copy.hero.dataLabel)}>{isoDay(facts.lastCapture, lang)}</Fact>
        <Fact label={t(copy.hero.listingsLabel)}>{integer(facts.listings, lang)}</Fact>
        <Fact label={t(copy.hero.errorLabel)}>
          {fill(copy.hero.errorValue, lang, {
            car: percent(facts.carMape * 100, lang),
            motorcycle: percent(facts.motorcycleMape * 100, lang),
          })}
        </Fact>
      </dl>
    </section>
  );
}
