"use client";

/**
 * A term with its definition attached, the first time the page uses it.
 *
 * A button rather than an `abbr` with a title: a title never shows on touch and is not
 * reliably read by screen readers. The definition opens on hover, on keyboard focus and on
 * tap, and is wired to the button with `aria-describedby`, so it is announced with the term.
 */

import { Fragment, useId, useState, type ReactNode } from "react";

import { useLang } from "./LanguageProvider";
import type { Lang, Localized } from "@/lib/i18n";

export function Term({ term, definition }: { term: Localized; definition: Localized }) {
  const { t } = useLang();
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={id}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        // Inline in running text: exempt from the 44 px touch floor (WCAG 2.5.8), which
        // would otherwise pull every line that carries a term apart.
        data-inline=""
        className="cursor-help border-b border-dotted border-muted text-inherit"
      >
        {t(term)}
      </button>
      <span
        id={id}
        role="tooltip"
        className={`absolute bottom-full left-0 z-20 mb-2 w-[min(18rem,80vw)] rounded-md border border-line-strong bg-surface-2 p-3 text-left text-detail font-normal text-ink ${
          open ? "block" : "hidden"
        }`}
      >
        {t(definition)}
      </span>
    </span>
  );
}

/**
 * `fill` for sentences that carry a component, such as a `Term`, in a placeholder.
 *
 * Splits the sentence on `{placeholders}` and puts each value in its place, string or
 * node. Throws on a placeholder with no value, like `fill`, so a forgotten one fails the
 * static build instead of shipping braces.
 */
export function fillNodes(
  text: Localized,
  lang: Lang,
  vars: Record<string, ReactNode>,
): ReactNode {
  const parts = text[lang].split(/(\{\w+\})/g);
  return parts.map((part, index) => {
    const match = /^\{(\w+)\}$/.exec(part);
    if (!match) return <Fragment key={index}>{part}</Fragment>;
    const key = match[1] as string;
    if (!(key in vars)) throw new Error(`i18n: no value for {${key}} in "${text[lang]}"`);
    return <Fragment key={index}>{vars[key]}</Fragment>;
  });
}
