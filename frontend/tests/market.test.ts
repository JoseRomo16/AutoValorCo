import { describe, expect, it } from "vitest";

import { signedCop } from "@/lib/format";
import { isWideInterval, mileageByQuartile, spreadLabels, withOrigin } from "@/lib/market";
import { mileageEffect } from "@/lib/results";

describe("isWideInterval", () => {
  it("flags Volkswagen's 1,9–8,1 % around 5,1 %", () => {
    expect(isWideInterval(5.08, 1.91, 8.15)).toBe(true);
  });

  it("leaves a tight interval alone", () => {
    // Kia on cars: 4,6–5,8 % around 5,2 %.
    expect(isWideInterval(5.2, 4.61, 5.78)).toBe(false);
  });

  it("reads magnitude, not sign", () => {
    expect(isWideInterval(-2, -3, -1.5)).toBe(false);
    expect(isWideInterval(-2, -5, 0.5)).toBe(true);
  });
});

describe("mileageByQuartile", () => {
  const rows = mileageEffect();

  it.each(["car", "motorcycle"] as const)("keeps %s apart, Q1 to Q4, whole group aside", (v) => {
    const { all, quartiles } = mileageByQuartile(rows, v);
    expect(all?.segment).toBe("all");
    expect(quartiles.map((row) => row.segment)).toEqual(["Q1", "Q2", "Q3", "Q4"]);
    expect(quartiles.every((row) => row.vehicle_type === v)).toBe(true);
  });
});

describe("withOrigin", () => {
  it("starts the curve at 100 % at age 0", () => {
    const points = withOrigin([
      { age: 1, retained: 94.9 },
      { age: 2, retained: 90.1 },
    ]);
    expect(points[0]).toEqual({ age: 0, retained: 100 });
    expect(points).toHaveLength(3);
  });

  it("does not add a second origin", () => {
    const points = [{ age: 0, retained: 100 }];
    expect(withOrigin(points)).toBe(points);
  });
});

describe("spreadLabels", () => {
  it("leaves labels that already fit where they are", () => {
    expect(spreadLabels([10, 50, 90], 14, 0, 100)).toEqual([10, 50, 90]);
  });

  it("pushes overlapping labels apart, keeping their order", () => {
    const placed = spreadLabels([50, 52, 51], 14, 0, 200);
    const [a, b, c] = placed as [number, number, number];
    expect(Math.min(Math.abs(a - b), Math.abs(a - c), Math.abs(b - c))).toBeGreaterThanOrEqual(14);
    expect(a).toBeLessThan(c);
    expect(c).toBeLessThan(b);
  });

  it("stays inside the bottom edge", () => {
    const placed = spreadLabels([95, 96, 97], 14, 0, 100);
    expect(Math.max(...placed)).toBeLessThanOrEqual(100);
  });
});

describe("signedCop", () => {
  it("always carries the sign", () => {
    expect(signedCop(28971, "es").startsWith("+")).toBe(true);
    expect(signedCop(-108807, "es").startsWith("−")).toBe(true);
  });
});
