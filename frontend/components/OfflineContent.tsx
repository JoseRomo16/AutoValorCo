"use client";

/**
 * What the service worker shows for a page it never saved, with no connection.
 *
 * Precached like the three pages, so it is always there offline. It says what still works
 * without a network, Market and Methodology, which read files baked into the export, and
 * that Value needs the service to compute a price.
 */

import Link from "next/link";

import { useLang } from "@/components/LanguageProvider";
import { PageTitle } from "@/components/PageTitle";
import { WRAP } from "@/components/SiteChrome";
import { copy } from "@/lib/i18n";

const PAGES = [
  { href: "/mercado/", label: copy.nav.market },
  { href: "/metodologia/", label: copy.nav.method },
] as const;

export function OfflineContent() {
  const { t } = useLang();
  return (
    <div className={`${WRAP} py-20 sm:py-28`}>
      <PageTitle title={copy.titles.offline} />
      <div className="max-w-[48ch]">
        <p className="font-mono text-sm uppercase tracking-[0.1em] text-accent-text">
          {t(copy.pwa.offline.code)}
        </p>
        <h1 className="mt-3 font-display text-4xl font-bold leading-[1.1] [font-stretch:112%] sm:text-5xl">
          {t(copy.pwa.offline.title)}
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-muted">{t(copy.pwa.offline.body)}</p>
        <nav aria-label={t(copy.pwa.offline.pages)} className="mt-10 border-t border-line pt-6">
          <ul className="flex flex-wrap gap-x-7 gap-y-2.5">
            {PAGES.map((page) => (
              <li key={page.href}>
                <Link
                  href={page.href}
                  prefetch={false}
                  className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-4 hover:opacity-80 sm:min-h-6"
                >
                  {t(page.label)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  );
}
