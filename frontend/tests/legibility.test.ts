import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Nothing on the market page is set under 13 px.
 *
 * Tailwind's `text-xs` is 12 px, and it carried the chart notes ("no se distingue de
 * cero", the medians, the intervals) and the tooltips until the copy review read them on a
 * phone. The data sizes are tokens in `globals.css` (`text-caption` 13, `text-detail` 14,
 * `text-label` 15, `text-value` 16); this fails on anything smaller in the files that draw
 * the page. Block 8 adds Methodology's files to the list.
 */

const ROOT = process.cwd();
const FILES = [
  "components/MarketDashboard.tsx",
  "components/VehicleTabs.tsx",
  "components/charts/BrandPicker.tsx",
  "components/charts/IntervalBars.tsx",
  "components/charts/RetainedCurves.tsx",
  "components/charts/ShareBar.tsx",
];
const MIN_PX = 13;

/** Every font size a line sets, in px, with what set it. */
function sizes(line: string): { px: number; what: string }[] {
  const found: { px: number; what: string }[] = [];
  for (const match of line.matchAll(/\btext-(xs|2xs)\b/g)) {
    found.push({ px: match[1] === "xs" ? 12 : 10, what: match[0] });
  }
  for (const match of line.matchAll(/\btext-\[(\d+(?:\.\d+)?)(px|rem)\]/g)) {
    const value = Number(match[1]);
    found.push({ px: match[2] === "rem" ? value * 16 : value, what: match[0] });
  }
  for (const match of line.matchAll(/\b(?:fontSize|FONT)\s*[:=]\s*(\d+(?:\.\d+)?)\b/g)) {
    found.push({ px: Number(match[1]), what: match[0] });
  }
  return found;
}

describe("type sizes on the market page", () => {
  it("knows what small looks like", () => {
    // Guards the scanner: a broken regex would pass every file below.
    expect(sizes('className="text-xs text-[11px]" fontSize: 10').map((s) => s.px)).toEqual([
      12, 11, 10,
    ]);
  });

  it.each(FILES)("%s sets nothing under 13 px", (file) => {
    const small = readFileSync(path.join(ROOT, file), "utf8")
      .split("\n")
      .flatMap((line, index) =>
        sizes(line)
          .filter(({ px }) => px < MIN_PX)
          .map(({ what }) => `${index + 1}: ${what}`),
      );
    expect(small).toEqual([]);
  });

  it("keeps a floor under the bar labels on phones", () => {
    // jsdom has no layout, so this pins the two classes that prevent the bug seen in
    // Chrome at 320 px: with breaks allowed anywhere and no minimum, a long note in the
    // figure column squeezed "Norte de Santander" into a column one letter wide.
    const bars = readFileSync(path.join(ROOT, "components/charts/IntervalBars.tsx"), "utf8");
    expect(bars).toContain("grid-cols-[minmax(7rem,1fr)_auto]");
    expect(bars).not.toContain("[overflow-wrap:anywhere]");
  });

  it("publishes the data sizes as tokens", () => {
    const css = readFileSync(path.join(ROOT, "app", "globals.css"), "utf8");
    for (const [token, rem] of [
      ["caption", "0.8125rem"],
      ["detail", "0.875rem"],
      ["label", "0.9375rem"],
      ["value", "1rem"],
    ]) {
      expect(css).toContain(`--text-${token}: ${rem};`);
    }
  });
});
