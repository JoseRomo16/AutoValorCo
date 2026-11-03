import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { MarketDashboard } from "@/components/MarketDashboard";
import { copy } from "@/lib/i18n";
import { isThin } from "@/lib/listings";
import {
  catalogueContrast,
  depreciation,
  manifest,
  mileageEffect,
  regionalEffect,
  retainedValue,
} from "@/lib/results";

/**
 * The market page on the committed result tables, the same files the static export reads.
 *
 * Expectations are derived from those tables, not typed: a retrain moves every figure and
 * these tests should keep asserting the rule rather than last week's number.
 */

const regional = regionalEffect();
const thinMoto = regional.filter((row) => row.vehicle_type === "motorcycle" && isThin(row.listings));

function show() {
  return render(
    <LanguageProvider>
      <MarketDashboard
        manifest={manifest()}
        depreciation={depreciation()}
        retained={retainedValue()}
        mileage={mileageEffect()}
        regional={regional}
        contrast={catalogueContrast()}
      />
    </LanguageProvider>,
  );
}

beforeEach(() => window.localStorage.clear());

describe("the regional chart", () => {
  it("has thin departments to test against", () => {
    // If the lake fills in, the rule below goes vacuous; this says so instead.
    expect(thinMoto.length).toBeGreaterThan(0);
  });

  it("lists thin departments last, each with the few-listings note", () => {
    show();
    const lists = screen.getAllByRole("list");
    const motoList = lists.find((list) =>
      thinMoto.every((row) => list.textContent?.includes(row.department)),
    );
    expect(motoList).toBeDefined();
    const items = [...motoList!.querySelectorAll("li")];
    const tail = items.slice(-thinMoto.length);
    for (const item of tail) {
      expect(thinMoto.some((row) => item.textContent?.includes(row.department))).toBe(true);
      expect(item.textContent).toContain(copy.market.regional.fewListings.es);
    }
  });

  it("never quotes a thin department as an extreme in the reading", () => {
    const { container } = show();
    const reading = [...container.querySelectorAll("section")]
      .find((section) =>
        section.querySelector("h2")?.textContent?.includes(copy.market.regional.title.es),
      )
      ?.querySelector(":scope > p")?.textContent;
    expect(reading).toBeTruthy();
    for (const row of thinMoto) {
      expect(reading).not.toContain(row.department);
    }
  });
});

describe("the retained-value legend", () => {
  it("reads the last point as a share at an age", () => {
    const oldest = Math.max(...retainedValue().map((row) => row.age_years));
    show();
    expect(screen.getAllByText(new RegExp(`a los ${oldest} años$`)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/% · \d+$/)).toBeNull();
  });
});
