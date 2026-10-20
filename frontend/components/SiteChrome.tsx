"use client";

/**
 * Header, navigation, language switch and footer.
 *
 * One client component rather than three, because all of it reads the language and
 * splitting it would only multiply context consumers. No third-party logos anywhere: the
 * mark is the project's own name.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLang } from "./LanguageProvider";
import { LANGS, copy } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

const REPO_URL = "https://github.com/JoseRomo16/AutoValorCo";
const API_DOCS_URL = "https://autovalor-api.onrender.com/docs";

const NAV = [
  { href: "/", label: copy.nav.value },
  { href: "/mercado/", label: copy.nav.market },
  { href: "/metodologia/", label: copy.nav.method },
] as const;

function LanguageToggle() {
  const { lang, setLang, t } = useLang();
  return (
    <div
      className="flex items-center gap-1 rounded-full border border-slate-300 p-0.5 dark:border-slate-700"
      role="group"
      aria-label={t(copy.lang.label)}
    >
      {LANGS.map((candidate: Lang) => (
        <button
          key={candidate}
          type="button"
          onClick={() => setLang(candidate)}
          aria-pressed={lang === candidate}
          className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
            lang === candidate
              ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
              : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          }`}
        >
          {candidate.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function SiteHeader() {
  const { t } = useLang();
  const pathname = usePathname();

  return (
    <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-baseline gap-2">
          <span className="text-lg font-semibold tracking-tight">AutoValor</span>
          <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-xs font-bold text-white">
            CO
          </span>
        </Link>

        <nav aria-label={t(copy.site.name)} className="order-last w-full sm:order-none sm:w-auto">
          <ul className="flex gap-1">
            {NAV.map((item) => {
              const active = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    // Off because this is a static export: Next prefetches a per-segment
                    // payload that the exported tree does not contain, so every link
                    // produced a 404 in the console and then fell back to a normal
                    // navigation anyway. Three HTML pages do not need prefetching.
                    prefetch={false}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-md px-3 py-1.5 text-sm font-medium transition ${
                      active
                        ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                    }`}
                  >
                    {t(item.label)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto">
          <LanguageToggle />
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  const { t } = useLang();
  return (
    <footer className="mt-16 border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50">
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8 text-sm text-slate-600 sm:px-6 dark:text-slate-400">
        <p className="max-w-3xl">{t(copy.footer.disclaimer)}</p>
        <p className="flex flex-wrap gap-x-6 gap-y-1">
          <a className="underline hover:no-underline" href={REPO_URL}>
            {t(copy.footer.repo)}
          </a>
          <a className="underline hover:no-underline" href={API_DOCS_URL}>
            {t(copy.footer.api)}
          </a>
        </p>
      </div>
    </footer>
  );
}

export { REPO_URL, API_DOCS_URL };
