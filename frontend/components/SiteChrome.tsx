"use client";

/**
 * Header, navigation, the language and theme switches, and the footer.
 *
 * One client component rather than several, because all of it reads the language and
 * splitting it would only multiply context consumers. No third-party logos anywhere: the
 * mark is the project's own name, with "CO" set as a Colombian private plate — yellow
 * field, black keyline. That is where the accent colour comes from, so the logo is the one
 * place it gets to be literal.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useLang } from "./LanguageProvider";
import { THEMES, useTheme } from "./ThemeProvider";
import type { Theme } from "./ThemeProvider";
import { isoDay, modelDate } from "@/lib/format";
import { LANGS, copy, fill } from "@/lib/i18n";
import type { Lang, Localized } from "@/lib/i18n";

const REPO_URL = "https://github.com/JoseRomo16/AutoValorCo";
const API_DOCS_URL = "https://autovalor-api.onrender.com/docs";
const LINKEDIN_URL = "https://www.linkedin.com/in/jose-luis-romo-dev-data";

const NAV = [
  { href: "/", label: copy.nav.value },
  { href: "/mercado/", label: copy.nav.market },
  { href: "/metodologia/", label: copy.nav.method },
] as const;

/** The site's one content width. Pages that need something narrower say so themselves. */
export const WRAP = "mx-auto w-full max-w-[1120px] px-5 sm:px-6";

function Plate() {
  // The doubled outline is what a real plate has: a black keyline inside a yellow field.
  return (
    <span className="inline-block rounded-[3px] border-[1.5px] border-[#111] bg-accent px-1.5 pb-[3px] pt-1 font-mono text-[11px] leading-none text-[#111] shadow-[0_0_0_1.5px_var(--accent)]">
      CO
    </span>
  );
}

function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span className="font-display text-[1.1875rem] font-extrabold tracking-[-0.01em] [font-stretch:112%]">
        AutoValor
      </span>
      <Plate />
    </span>
  );
}

/**
 * A segmented control.
 *
 * Shared by language and theme because they are the same object: a small set of mutually
 * exclusive choices where the current one is filled. Mono, because the segments have to
 * stay the same width when the label changes and a proportional face would make the
 * control twitch.
 */
function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex rounded-md border border-line p-0.5 font-mono text-xs"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={`min-h-10 rounded px-2.5 transition-colors duration-200 ease-[var(--ease-out-soft)] sm:min-h-0 sm:py-1.5 ${
            value === option.value
              ? "bg-ink text-ground"
              : "text-muted hover:text-ink"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function SiteHeader() {
  const { lang, setLang, t } = useLang();
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // The hairline and the blur only appear once the page has moved, so the header is part
  // of the hero at rest and becomes a surface when it starts overlapping content.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const tools = (
    <>
      <Segmented
        label={t(copy.lang.label)}
        value={lang}
        onChange={setLang}
        options={LANGS.map((candidate: Lang) => ({
          value: candidate,
          label: candidate.toUpperCase(),
        }))}
      />
      <Segmented
        label={t(copy.theme.label)}
        value={theme}
        onChange={setTheme}
        options={THEMES.map((candidate: Theme) => ({
          value: candidate,
          label: t(copy.theme[candidate]),
        }))}
      />
    </>
  );

  return (
    <header
      className={`veil sticky top-0 z-20 backdrop-blur-[14px] backdrop-saturate-150 transition-[border-color] duration-200 ${
        scrolled ? "border-b border-line" : "border-b border-transparent"
      }`}
    >
      <div className={`${WRAP} flex min-h-[60px] flex-wrap items-center gap-x-8`}>
        <Link href="/" prefetch={false} aria-label="AutoValor CO" className="py-2">
          <Wordmark />
        </Link>

        <nav aria-label={t(copy.site.name)} className="order-3 w-full pb-2 sm:order-none sm:w-auto sm:pb-0">
          <ul className="flex gap-1">
            {NAV.map((item) => {
              const active = pathname === item.href;
              return (
                <li key={item.href} className="flex-1 sm:flex-none">
                  <Link
                    href={item.href}
                    // Off because this is a static export: Next prefetches a per-segment
                    // payload that the exported tree does not contain, so every link
                    // produced a 404 in the console and then fell back to a normal
                    // navigation anyway. Three HTML pages do not need prefetching.
                    prefetch={false}
                    // Closing on the click rather than on the route change: a phone should
                    // not land on the next page with the settings tray still hanging open,
                    // and the navigation is the event that causes it.
                    onClick={() => setOpen(false)}
                    aria-current={active ? "page" : undefined}
                    className={`grid min-h-11 place-items-center rounded-md px-3 text-sm transition-colors duration-200 sm:min-h-0 sm:py-1.5 ${
                      active
                        ? "bg-accent font-semibold text-accent-ink"
                        : "text-muted hover:bg-surface hover:text-ink"
                    }`}
                  >
                    {t(item.label)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="site-tools"
          className="ml-auto grid min-h-11 min-w-11 place-items-center rounded-md border border-line px-3 font-mono text-xs text-muted sm:hidden"
        >
          {t(copy.nav.settings)}
        </button>

        <div
          id="site-tools"
          className={`order-4 w-full justify-between gap-2 pb-2 sm:order-none sm:ml-auto sm:flex sm:w-auto sm:gap-2 sm:pb-0 ${
            open ? "flex" : "hidden"
          }`}
        >
          {tools}
        </div>
      </div>
    </header>
  );
}

function FooterColumn({ title, children }: { title: Localized; children: React.ReactNode }) {
  const { t } = useLang();
  return (
    <div>
      <h2 className="mb-3 font-mono text-xs uppercase tracking-[0.1em] text-faint">{t(title)}</h2>
      <ul className="grid gap-2 text-sm">{children}</ul>
    </div>
  );
}

function FooterLink({ href, children }: { href: string; children: React.ReactNode }) {
  const external = href.startsWith("http");
  const className = "text-muted transition-colors duration-200 hover:text-ink hover:underline";
  return (
    <li>
      {external ? (
        <a className={className} href={href}>
          {children}
        </a>
      ) : (
        <Link className={className} href={href} prefetch={false}>
          {children}
        </Link>
      )}
    </li>
  );
}

/**
 * The footer.
 *
 * `dataDate` and `modelDate` are passed in rather than read here: both come from files in
 * the repository, and this is a client component with no filesystem. The layout reads them
 * once at build time, which also keeps every page agreeing about what day the data is from.
 */
export function SiteFooter({
  dataDate,
  modelVersion,
}: {
  dataDate?: string;
  modelVersion?: string;
}) {
  const { lang, t } = useLang();

  return (
    <footer className="mt-auto border-t border-line bg-band pb-10 pt-12">
      <div className={WRAP}>
        <div className="grid gap-10 sm:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <Link href="/" prefetch={false} aria-label="AutoValor CO">
              <Wordmark />
            </Link>
            <p className="mt-4 max-w-[46ch] text-sm text-muted">{t(copy.footer.disclaimer)}</p>
          </div>

          <FooterColumn title={copy.footer.productTitle}>
            {NAV.map((item) => (
              <FooterLink key={item.href} href={item.href}>
                {t(item.label)}
              </FooterLink>
            ))}
          </FooterColumn>

          <FooterColumn title={copy.footer.projectTitle}>
            <FooterLink href={REPO_URL}>{t(copy.footer.repo)}</FooterLink>
            <FooterLink href={API_DOCS_URL}>{t(copy.footer.api)}</FooterLink>
            <FooterLink href={LINKEDIN_URL}>{t(copy.footer.linkedin)}</FooterLink>
          </FooterColumn>
        </div>

        <div className="mt-9 flex flex-wrap justify-between gap-x-6 gap-y-2 border-t border-line pt-5 font-mono text-xs text-faint">
          <span>{t(copy.footer.author)}</span>
          {dataDate && modelVersion && (
            <span>
              {`${fill(copy.footer.dataDate, lang, { date: isoDay(dataDate, lang) })} · ${t(
                copy.footer.modelLabel,
              )} ${modelDate(modelVersion, lang)}`}
            </span>
          )}
        </div>
      </div>
    </footer>
  );
}

export { REPO_URL, API_DOCS_URL, LINKEDIN_URL };
