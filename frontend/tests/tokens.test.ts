import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The contrast of every text token against every surface it can land on.
 *
 * This exists because the audit's numbers went stale between two blocks: a light `--faint`
 * reported at 4.29:1 had already been fixed by the time anyone acted on it, and a dark pair
 * nobody had measured was the one actually broken. Contrast is arithmetic over values in a
 * file, so it should be a test rather than something re-measured by hand in a browser and
 * written into a document that ages.
 *
 * What it cannot see: colour that is not a token. A Tailwind utility with a literal, or a
 * chart fill written in a component, is outside this file -- which is part of why Blocks 7
 * and 8 move the charts onto tokens.
 */

const CSS = readFileSync(path.join(process.cwd(), "app", "globals.css"), "utf8");

/** WCAG 2.1 AA for body text. */
const AA = 4.5;

/**
 * How far apart `--muted` and `--faint` have to read as two levels of emphasis.
 *
 * Dark only. In the light theme the two cannot be pulled further apart without breaking
 * AA -- `--faint` is the lighter of the pair there, so more separation means less contrast
 * against paper, and the current 1.26:1 is what fits under that ceiling. Asserting the
 * same floor in both themes would mean choosing which rule to break.
 */
const SEPARATION = 1.5;

const TEXT = ["ink", "muted", "faint"] as const;
const SURFACES = ["ground", "band", "surface", "surface-2"] as const;

/** Read one theme's token block: bare `:root` is dark, the attribute selector is light. */
function tokens(selector: string): Record<string, string> {
  const start = CSS.indexOf(selector);
  if (start === -1) throw new Error(`no ${selector} block in globals.css`);
  const open = CSS.indexOf("{", start);
  const block = CSS.slice(open, CSS.indexOf("\n}", open));

  const found: Record<string, string> = {};
  for (const match of block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    found[match[1] as string] = match[2] as string;
  }
  return found;
}

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => parseInt(value.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (linear[0] as number) + 0.7152 * (linear[1] as number) + 0.0722 * (linear[2] as number);
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (high + 0.05) / (low + 0.05);
}

const THEMES = {
  // Bare `:root` is the dark theme, and also what renders with JavaScript off.
  dark: tokens(":root {"),
  light: tokens(':root[data-theme="light"]'),
};

describe("the colour tokens", () => {
  for (const [theme, values] of Object.entries(THEMES)) {
    it(`defines every token the contrast rules cover, in ${theme}`, () => {
      // Otherwise a renamed token would make the loops below silently check nothing.
      for (const name of [...TEXT, ...SURFACES]) {
        expect(values[name], `--${name} missing in ${theme}`).toMatch(/^#[0-9a-f]{6}$/i);
      }
    });

    for (const text of TEXT) {
      for (const surface of SURFACES) {
        it(`reads ${text} on ${surface} at AA in ${theme}`, () => {
          const ratio = contrast(values[text] as string, values[surface] as string);
          expect(
            Number(ratio.toFixed(2)),
            `--${text} on --${surface} in ${theme} is ${ratio.toFixed(2)}:1`,
          ).toBeGreaterThanOrEqual(AA);
        });
      }
    }
  }

  it("keeps faint visibly fainter than muted in dark", () => {
    // They were #d4cfc2 and #c2bdb0: 1.21:1 apart, which is two names for one colour.
    const ratio = contrast(THEMES.dark.muted as string, THEMES.dark.faint as string);
    expect(Number(ratio.toFixed(2))).toBeGreaterThanOrEqual(SEPARATION);
  });

  it("keeps faint on the dim side of muted in light", () => {
    // The direction still has to hold even where the gap cannot be widened: faint is the
    // lighter of the two on paper, so it recedes.
    expect(luminance(THEMES.light.faint as string)).toBeGreaterThan(
      luminance(THEMES.light.muted as string),
    );
  });
});
