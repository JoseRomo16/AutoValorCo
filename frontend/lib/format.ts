/**
 * Number formatting, which is a product decision rather than a utility.
 *
 * Colombian pesos run to eight digits, so a raw `89000000` is unreadable and a rounded
 * `89 M` hides the precision the model actually has. Both forms are produced: the full
 * amount where the number is the answer, the compact one where it is a label on a chart.
 */

import type { Lang } from "./i18n";

const LOCALE: Record<Lang, string> = { es: "es-CO", en: "en-US" };

/**
 * The space between a figure and its unit: U+00A0, built from its code point so it cannot
 * be mistaken for an ordinary space by anyone reading or editing this line.
 *
 * With an ordinary space the browser is free to wrap "63" and "%" onto separate lines, and
 * a percentage that loses its sign reads as a different number.
 */
const NBSP = String.fromCharCode(0xa0);

/** Full peso amount, no cents: "$ 89.000.000" / "COP 89,000,000". */
export function cop(value: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Peso amount in millions, spelled out: "$ 89 millones" / "COP 89M".
 *
 * The old form was "89 M", which a reader has to decode. Spanish says the word; English
 * keeps the suffix, which is how prices are written there.
 */
export function copMillions(value: number, lang: Lang): string {
  const millions = value / 1_000_000;
  const digits = Math.abs(millions) >= 10 ? 0 : 1;
  const formatted = new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(millions);
  return lang === "es" ? `$${NBSP}${formatted} millones` : `COP${NBSP}${formatted}M`;
}

/** Compact peso amount for a chart label, where the word does not fit: "89 M" / "89M". */
export function copCompact(value: number, lang: Lang): string {
  const millions = value / 1_000_000;
  const digits = Math.abs(millions) >= 10 ? 0 : 1;
  const formatted = new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(millions);
  return lang === "es" ? `${formatted}${NBSP}M` : `${formatted}M`;
}

/**
 * A plain decimal in the reader's locale: "4,9" / "4.9".
 *
 * `toFixed` always writes a point, so a ratio printed with it read as "4.9" on the Spanish
 * page while every percentage next to it used a comma.
 */
export function decimal(value: number, lang: Lang, digits = 1): string {
  return new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
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
  return lang === "es" ? `${formatted}${NBSP}%` : `${formatted}%`;
}

/** Percentage points, the unit of a difference between two percentages. */
export function points(value: number, lang: Lang, digits = 1): string {
  const formatted = new Intl.NumberFormat(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  return lang === "es" ? `${formatted}${NBSP}puntos` : `${formatted}${NBSP}points`;
}

/** Same as `percent`, but always carrying its sign, for a difference against a reference. */
export function signedPercent(value: number, lang: Lang, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${percent(Math.abs(value), lang, digits)}`;
}

/** A multiplicative SHAP factor as the percentage it moves the price: 1.15 -> "+15 %". */
export function factorAsPercent(factor: number, lang: Lang): string {
  return signedPercent((factor - 1) * 100, lang, 1);
}

/** Kilometres with their unit, which must not wrap away from the figure. */
export function kilometres(value: number, lang: Lang): string {
  return `${integer(value, lang)}${NBSP}km`;
}

/** An ISO timestamp as a plain date, which is the only part that matters here. */
export function isoDate(value: string, lang: Lang): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "long", timeZone: "UTC" }).format(date);
}

/** An ISO date with no time, as a long readable one: "19 de octubre de 2026". */
export function isoDay(value: string, lang: Lang): string {
  return isoDate(`${value}T00:00:00Z`, lang);
}

/**
 * A date as the month it falls in: "marzo de 2027" / "March 2027".
 *
 * For a date that is a forecast rather than an event. The price index becomes possible once
 * six months of captures have accumulated, and printing the exact day of that arithmetic
 * claims a precision the estimate does not have.
 */
export function isoMonth(value: string, lang: Lang): string {
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(LOCALE[lang], {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

/**
 * The served model's version as a date a reader recognises.
 *
 * The version is `2026-10-25.12948`: the day it was trained and the size of the lake behind
 * it, which is what tells two models apart and is also the wrong thing to print on a page.
 * Only the date survives into the copy.
 */
export function modelDate(version: string, lang: Lang): string {
  const [day] = version.split(".");
  const parsed = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return version;
  return new Intl.DateTimeFormat(LOCALE[lang], {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}
