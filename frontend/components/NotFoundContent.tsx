"use client";

/**
 * The 404.
 *
 * It was Next's default page: English only, on pure black whatever the visitor's theme,
 * and with no way back into the site. A static export serves this file for every unmatched
 * path, so it is the page a mistyped or stale link lands on — the one place where somebody
 * who is already lost meets the product for the first time.
 *
 * The translated half. A client component because the copy is translated at runtime: a static export has no
 * server to negotiate language with, so every translated page on this site is a client
 * component (see `LanguageProvider`). The header and footer come from the layout, so the
 * theme, the language toggle and the nav are all already here.
 */

import Link from "next/link";

import { useLang } from "@/components/LanguageProvider";
import { PageTitle } from "@/components/PageTitle";
import { WRAP } from "@/components/SiteChrome";
import { copy } from "@/lib/i18n";

const PAGES = [
  { href: "/", label: copy.nav.value },
  { href: "/mercado/", label: copy.nav.market },
  { href: "/metodologia/", label: copy.nav.method },
] as const;

export function NotFoundContent() {
  const { t } = useLang();

  return (
    <div className={`${WRAP} py-20 sm:py-28`}>
      <PageTitle title={copy.titles.notFound} />
      <div className="max-w-[48ch]">
        <p className="font-mono text-sm uppercase tracking-[0.1em] text-accent-text">
          {t(copy.notFound.code)}
        </p>
        <h1 className="mt-3 font-display text-4xl font-bold leading-[1.1] [font-stretch:112%] sm:text-5xl">
          {t(copy.notFound.title)}
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-muted">{t(copy.notFound.body)}</p>

        <Link
          href="/"
          prefetch={false}
          className="mt-8 inline-flex min-h-12 items-center justify-center rounded-md bg-accent px-5.5 font-semibold text-accent-ink transition-[filter,transform] duration-200 hover:brightness-105 active:translate-y-px"
        >
          {t(copy.notFound.back)}
        </Link>

        <nav aria-label={t(copy.notFound.pages)} className="mt-10 border-t border-line pt-6">
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
