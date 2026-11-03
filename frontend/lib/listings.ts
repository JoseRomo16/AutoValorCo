/**
 * Where a department stops having enough listings to be read like the others.
 *
 * Fifty rather than a rounder number because that is where the catalogue actually splits:
 * three of ten car departments sit under it (Cauca 1, Meta 2, Quindío 12) and the next one
 * up has an order of magnitude more. The valuation form and the market's regional chart
 * use the same line, so a department the form calls thin is never presented as solid on the
 * chart next door. It is a product rule, not a measured figure.
 */
export const LOW_DATA_LISTINGS = 50;

export function isThin(listings: number): boolean {
  return listings < LOW_DATA_LISTINGS;
}

/**
 * Regional rows in reading order: well-covered departments by effect, highest first, then
 * the thin ones, also by effect.
 *
 * A department with 43 listings used to sit at the bottom of the motorcycle chart as the
 * cheapest region in the country, and the reading quoted it as such. Its interval said
 * otherwise, but an interval is easy to miss; its place in the list is not.
 */
export function orderRegions<T extends { pct_change: number; listings: number }>(rows: T[]): T[] {
  const byEffect = (a: T, b: T) => b.pct_change - a.pct_change;
  return [
    ...rows.filter((row) => !isThin(row.listings)).sort(byEffect),
    ...rows.filter((row) => isThin(row.listings)).sort(byEffect),
  ];
}
