/**
 * Pure rules behind the market page's charts, kept out of the components so they can be
 * tested without rendering anything.
 */

import type { MileageRow, VehicleType } from "./results";

/**
 * An interval wider than the estimate it surrounds.
 *
 * The bars are ordered by their central value, and a central value with a 1,9–8,1 %
 * interval around 5,1 % (Volkswagen on cars) cannot carry first place on its own. The line
 * is a ratio, not a figure: the interval spans more than the estimate is worth. Rows whose
 * interval crosses zero already say so with their own note, and are left to it.
 */
export function isWideInterval(value: number, low: number, high: number): boolean {
  return high - low > Math.abs(value);
}

/**
 * One vertical's mileage rows: the whole-group row apart, then the quartiles from the
 * cheapest to the dearest price class.
 *
 * The chart used to mix cars and motorcycles in one list sorted by value, so "Moto ·
 * Cuartil 3" sat between two car quartiles and the price-class reading was lost.
 */
export function mileageByQuartile(
  rows: MileageRow[],
  vertical: VehicleType,
): { all: MileageRow | undefined; quartiles: MileageRow[] } {
  const mine = rows.filter((row) => row.vehicle_type === vertical);
  return {
    all: mine.find((row) => row.segment === "all"),
    quartiles: mine
      .filter((row) => row.segment !== "all")
      .sort((a, b) => a.segment.localeCompare(b.segment, "en", { numeric: true })),
  };
}

export type CurvePoint = { age: number; retained: number };

/**
 * Start a retained-value curve at age 0 = 100 %.
 *
 * The published curves are `exp(slope × age)` from age 1, so the first year's drop was
 * invisible: the line began already below the top of an axis that starts at zero. At age 0
 * the same formula gives exactly 100 %, which is the curve's own starting point rather
 * than a measured price of new vehicles, and the chart's description says so.
 */
export function withOrigin(points: CurvePoint[]): CurvePoint[] {
  if (points.some((point) => point.age === 0)) return points;
  return [{ age: 0, retained: 100 }, ...points];
}

/**
 * Push end-of-line labels apart so none overprints another.
 *
 * Takes the y each label wants (its line's last point) and returns where to draw it, in
 * the same order. Labels move the least needed to sit `gap` apart and stay inside
 * `[top, bottom]`; the line still ends at its true value.
 */
export function spreadLabels(wanted: number[], gap: number, top: number, bottom: number): number[] {
  const order = wanted.map((y, index) => ({ y, index })).sort((a, b) => a.y - b.y);
  const placed = order.map((entry) => entry.y);
  for (let i = 1; i < placed.length; i += 1) {
    placed[i] = Math.max(placed[i] as number, (placed[i - 1] as number) + gap);
  }
  const overflow = (placed.at(-1) ?? bottom) - bottom;
  if (overflow > 0) {
    for (let i = placed.length - 1; i >= 0; i -= 1) {
      const limit = i === placed.length - 1 ? bottom : (placed[i + 1] as number) - gap;
      placed[i] = Math.min(placed[i] as number, limit);
    }
  }
  const result: number[] = new Array(wanted.length);
  order.forEach((entry, rank) => {
    result[entry.index] = Math.max(top, placed[rank] as number);
  });
  return result;
}
