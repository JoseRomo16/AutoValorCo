import { describe, expect, it } from "vitest";

import { copy, type Localized } from "@/lib/i18n";

/**
 * Checks over every string the site renders.
 *
 * Read from the `copy` object itself rather than by parsing `i18n.ts` as text, so a key
 * that is built, spread or nested deeper than expected is still walked.
 */

type Leaf = { path: string; text: Partial<Localized> };

/**
 * Every `{ es, en }` pair, by its dotted path. An object counts as one when either key holds
 * a string, so a pair missing its other half is still found. `copy.lang` is the exception
 * the condition is written around: its `es` and `en` keys name the languages and hold pairs.
 */
function leaves(node: unknown, path = "copy"): Leaf[] {
  if (node === null || typeof node !== "object") return [];
  const record = node as Record<string, unknown>;
  if (typeof record.es === "string" || typeof record.en === "string") {
    return [{ path, text: record as Partial<Localized> }];
  }
  return Object.entries(record).flatMap(([key, child]) => leaves(child, `${path}.${key}`));
}

const ALL = leaves(copy);

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1] ?? "").sort();
}

describe("copy", () => {
  it("walks a meaningful number of strings", () => {
    // Guards the walker itself: a broken `leaves` would make every test below vacuous.
    expect(ALL.length).toBeGreaterThan(300);
  });

  it("has text in both languages for every key", () => {
    const missing = ALL.filter(
      ({ text }) =>
        typeof text.es !== "string" ||
        typeof text.en !== "string" ||
        text.es.trim() === "" ||
        text.en.trim() === "",
    ).map(({ path }) => path);
    expect(missing).toEqual([]);
  });

  it("uses the same placeholders in both languages", () => {
    // A `{department}` present in Spanish and missing in English renders a sentence that
    // lost its subject, and `fill` cannot notice: it only throws on a placeholder with no
    // value, not on a value with no placeholder.
    const mismatched = ALL.filter(
      ({ text }) =>
        JSON.stringify(placeholders(text.es ?? "")) !==
        JSON.stringify(placeholders(text.en ?? "")),
    ).map(({ path }) => path);
    expect(mismatched).toEqual([]);
  });

  /**
   * Wording the copy review retired, kept out for good.
   *
   * "dearest" is archaic for prices, and "asked at more" is not English. Both were in five
   * places before anyone read the English page aloud.
   */
  const RETIRED = [
    /\bdearest\b/i,
    /\basked at more\b/i,
    // The capture is paused (ADR 0005): a weekly claim is false until it resumes.
    /una vez por semana/i,
    /once a week/i,
  ];

  it.each(RETIRED)("never says %s", (pattern) => {
    const hits = ALL.filter(({ text }) => pattern.test(text.en ?? "") || pattern.test(text.es ?? ""))
      .map(({ path }) => path);
    expect(hits).toEqual([]);
  });
});
