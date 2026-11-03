import { describe, expect, it } from "vitest";

import { LOW_DATA_LISTINGS, isThin, orderRegions } from "@/lib/listings";

const row = (department: string, pct_change: number, listings: number) => ({
  department,
  pct_change,
  listings,
});

describe("orderRegions", () => {
  // The motorcycle table as published on 2026-11-02, trimmed: Norte de Santander and
  // Quindío are under the line and used to close the chart as the cheapest regions.
  const motorcycles = [
    row("Quindío", -24.5, 48),
    row("Atlántico", -16.5, 122),
    row("Norte de Santander", -14.8, 43),
    row("Bogotá D.C.", 0, 1498),
    row("Antioquia", 27.5, 1316),
  ];

  it("puts thin departments last, after every well-covered one", () => {
    expect(orderRegions(motorcycles).map((r) => r.department)).toEqual([
      "Antioquia",
      "Bogotá D.C.",
      "Atlántico",
      "Norte de Santander",
      "Quindío",
    ]);
  });

  it("does not reorder the input array", () => {
    const before = motorcycles.map((r) => r.department);
    orderRegions(motorcycles);
    expect(motorcycles.map((r) => r.department)).toEqual(before);
  });

  it("draws the line where the valuation form does", () => {
    expect(isThin(LOW_DATA_LISTINGS - 1)).toBe(true);
    expect(isThin(LOW_DATA_LISTINGS)).toBe(false);
  });
});
