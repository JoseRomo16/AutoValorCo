/**
 * Number formatting, which is a product decision rather than a utility.
 *
 * Colombian pesos run to eight digits, so a raw `89000000` is unreadable and a rounded
 * `89 M` hides the precision the model actually has. Both forms are produced: the full
 * amount where the number is the answer, the compact one where it is a label on a chart.
 */

import type { Lang } from "./i18n";

const LOCALE: Record<Lang, string> = { es: "es-CO", en: "en-US" };

/** Full peso amount, no cents: "$ 89.000.000" / "COP 89,000,000". */
export function cop(value: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Compact peso amount for chart labels: "89,0 M" / "89.0M". */
export function copCompact(value: number, lang: Lang): string {
  const millions = value / 1_000_000;
  const digits = Math.abs(millions) >= 10 ? 0 : 1;
  const formatted = new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(millions);
  return lang === "es" ? `${formatted} M` : `${formatted}M`;
}

/** Thousands-separated integer: "60.000" / "60,000". */
export function integer(value: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang], { maximumFractionDigits: 0 }).format(value);
}

/** A percentage already expressed in points: "4,8 %" / "4.8%". */
export function percent(value: number, lang: Lang, digits = 1): string {
  const formatted = new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  return lang === "es" ? `${formatted} %` : `${formatted}%`;
}

/** Same, but always carrying its sign, for a difference against a reference. */
export function signedPercent(value: number, lang: Lang, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${percent(Math.abs(value), lang, digits)}`;
}

/** A multiplicative SHAP factor as the percentage it moves the price: 1.15 -> "+15 %". */
export function factorAsPercent(factor: number, lang: Lang): string {
  return signedPercent((factor - 1) * 100, lang, 1);
}

/** An ISO timestamp as a plain date, which is the only part that matters here. */
export function isoDate(value: string, lang: Lang): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "long", timeZone: "UTC" }).format(date);
}
