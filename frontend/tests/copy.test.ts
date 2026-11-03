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

describe("the names the three pages and the API share", () => {
  // The canonical form of each term, in both languages. A label that says the same thing
  // another way ("Anuncios analizados", "held-out listings", "Modelo del …") makes a reader
  // wonder whether two pages are counting two different things.
  const CANONICAL = [
    { es: "Anuncios en total", en: "Listings in total", where: [copy.hero.listingsLabel, copy.method.data.facts.listings] },
    { es: "Anuncios para evaluar", en: "Listings for evaluation", where: [copy.method.cards.evaluatedLabel] },
    { es: "anuncios para evaluar", en: "listings for evaluation", where: [copy.terms.heldOut.term] },
    { es: "Error medio", en: "Average error", where: [copy.hero.errorLabel, copy.method.results.columnError] },
    { es: "versión del modelo", en: "model version", where: [copy.footer.modelLabel] },
    { es: "Versión del modelo", en: "Model version", where: [copy.result.modelVersion, copy.method.modelVersion] },
  ];

  it.each(CANONICAL)("says $es / $en the same way everywhere", ({ es, en, where }) => {
    for (const text of where) {
      expect(text.es).toContain(es);
      expect(text.en).toContain(en);
    }
  });

  it("no longer uses the retired variants", () => {
    const retired = [/anuncios analizados/i, /anuncios apartados/i, /anuncios de evaluación/i, /^Modelo del /];
    const retiredEn = [/listings analysed/i, /held-out listings/i, /listings held out/i, /model from/i];
    for (const { path, text } of ALL) {
      for (const pattern of retired) expect(text.es ?? "", path).not.toMatch(pattern);
      for (const pattern of retiredEn) expect(text.en ?? "", path).not.toMatch(pattern);
    }
  });
});
