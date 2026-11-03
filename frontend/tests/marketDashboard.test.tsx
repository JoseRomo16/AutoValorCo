import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { MarketDashboard } from "@/components/MarketDashboard";
import { percent } from "@/lib/format";
import { copy } from "@/lib/i18n";
import { isThin } from "@/lib/listings";
import { isWideInterval } from "@/lib/market";
import {
  catalogueContrast,
  depreciation,
  manifest,
  mileageEffect,
  regionalEffect,
  retainedValue,
} from "@/lib/results";
import { chooseVehicle } from "@/lib/vehicleChoice";

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

function section(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`no section #${id}`);
  return node;
}

function chooseMotorcycles(id: string) {
  act(() => {
    fireEvent.click(within(section(id)).getByRole("tab", { name: copy.form.motorcycles.es }));
  });
}

/** The visible bar rows of a section, in order, as their text. */
function rows(id: string): string[] {
  return [...section(id).querySelectorAll("ul[aria-hidden] > li")].map((li) => li.textContent ?? "");
}

function reading(id: string): string {
  return section(id).querySelector(":scope > div:last-child p:last-child")?.textContent ?? "";
}

beforeEach(() => {
  // The choice lives in memory as well as in storage, so a test that picked motorcycles
  // would otherwise leave the next one on them.
  chooseVehicle("car");
  window.localStorage.clear();
});

describe("the vehicle tabs", () => {
  it("switch every section at once", () => {
    show();
    chooseMotorcycles("regiones");
    for (const id of ["depreciacion", "valor-retenido", "kilometraje", "regiones"]) {
      expect(
        within(section(id)).getByRole("tab", { name: copy.form.motorcycles.es }),
      ).toHaveAttribute("aria-selected", "true");
    }
  });

  it("remember the choice", () => {
    const first = show();
    chooseMotorcycles("depreciacion");
    first.unmount();
    show();
    expect(
      within(section("kilometraje")).getByRole("tab", { name: copy.form.motorcycles.es }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("keep the tapped tabs still while the sections above change height", () => {
    // jsdom has no layout, so the move is staged: the tablist sits at 400 px before the
    // switch and at 100 px after it, as when depreciation above loses six rows.
    show();
    const tablist = within(section("kilometraje")).getByRole("tablist");
    const tops = [400, 100];
    tablist.getBoundingClientRect = () => ({ top: tops.shift() ?? 100 }) as DOMRect;
    const scrollBy = vi.spyOn(window, "scrollBy").mockImplementation(() => {});
    chooseMotorcycles("kilometraje");
    expect(scrollBy).toHaveBeenCalledWith({ top: -300, behavior: "instant" });
    scrollBy.mockRestore();
  });

  it("do not scroll when nothing moved", () => {
    show();
    const tablist = within(section("depreciacion")).getByRole("tablist");
    tablist.getBoundingClientRect = () => ({ top: 200 }) as DOMRect;
    const scrollBy = vi.spyOn(window, "scrollBy").mockImplementation(() => {});
    chooseMotorcycles("depreciacion");
    expect(scrollBy).not.toHaveBeenCalled();
    scrollBy.mockRestore();
  });

  it("move with the arrow keys", () => {
    show();
    const tablist = within(section("depreciacion")).getByRole("tablist");
    act(() => {
      fireEvent.keyDown(tablist, { key: "ArrowRight" });
    });
    expect(
      within(section("depreciacion")).getByRole("tab", { name: copy.form.motorcycles.es }),
    ).toHaveAttribute("aria-selected", "true");
  });
});

describe("the finding cards", () => {
  it("link to four sections that exist", () => {
    const { container } = show();
    const links = [...container.querySelectorAll('section[aria-label] a[href^="#"]')];
    expect(links).toHaveLength(4);
    for (const link of links) {
      expect(document.getElementById(link.getAttribute("href")!.slice(1))).not.toBeNull();
    }
  });
});

describe("the regional chart", () => {
  it("has thin departments to test against", () => {
    // If the lake fills in, the rule below goes vacuous; this says so instead.
    expect(thinMoto.length).toBeGreaterThan(0);
  });

  it("lists thin departments last, each with the few-listings note", () => {
    show();
    chooseMotorcycles("regiones");
    const tail = rows("regiones").slice(-thinMoto.length);
    for (const text of tail) {
      expect(thinMoto.some((row) => text.includes(row.department))).toBe(true);
      expect(text).toContain(copy.market.regional.fewListings.es);
    }
  });

  it("never quotes a thin department as an extreme in the reading", () => {
    show();
    const text = reading("regiones");
    expect(text).not.toBe("");
    for (const row of thinMoto) expect(text).not.toContain(row.department);
  });

  it("says the regression's figure is not the valuation model's", () => {
    show();
    expect(section("regiones").textContent).toContain(copy.market.regional.modelNote.es);
  });
});

describe("the mileage chart", () => {
  it("shows one vertical, whole group first, then Q1 to Q4", () => {
    show();
    const labels = rows("kilometraje").map((text) => text.split(/[+−$]/)[0]?.trim());
    expect(labels[0]).toBe(copy.market.mileage.segmentAll.es);
    expect(labels.slice(1).map((label) => label?.replace(/\D/g, ""))).toEqual(["1", "2", "3", "4"]);
    expect(rows("kilometraje")).toHaveLength(5);
  });

  it("signs positive effects", () => {
    const positive = mileageEffect().filter((row) => row.vehicle_type === "car" && row.cop_per_step > 0);
    expect(positive.length).toBeGreaterThan(0);
    show();
    expect(rows("kilometraje").filter((text) => text.includes("+$")).length).toBe(positive.length);
  });
});

describe("the depreciation chart", () => {
  it("marks every significant interval wider than its estimate", () => {
    const wide = depreciation().filter(
      (row) =>
        row.vehicle_type === "car" &&
        row.significant &&
        isWideInterval(row.annual_depreciation_pct, row.ci_low_pct, row.ci_high_pct),
    );
    expect(wide.length).toBeGreaterThan(0);
    show();
    const marked = rows("depreciacion").filter((text) => text.includes(copy.market.wideInterval.es));
    expect(marked).toHaveLength(wide.length);
    for (const row of wide) expect(marked.some((text) => text.includes(row.brand))).toBe(true);
  });
});

describe("the retained-value chart", () => {
  it("starts every curve at 100 % at age 0", () => {
    show();
    const table = section("valor-retenido").querySelector(".sr-only table");
    expect(table).not.toBeNull();
    const headers = [...table!.querySelectorAll("thead th")].map((th) => th.textContent);
    expect(headers[1]).toBe("A los 0 años");
    for (const row of table!.querySelectorAll("tbody tr")) {
      expect(row.querySelectorAll("td")[0]?.textContent).toBe(percent(100, "es", 0));
    }
  });

  it("reads the last point as a share at an age", () => {
    const oldest = Math.max(...retainedValue().map((row) => row.age_years));
    show();
    expect(screen.getAllByText(new RegExp(`a los ${oldest} años$`)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/% · \d+$/)).toBeNull();
  });
});

describe("chart descriptions", () => {
  it("state the conclusion from the data, not the axis names", () => {
    const cars = retainedValue().filter((row) => row.vehicle_type === "car");
    const oldest = Math.max(...cars.map((row) => row.age_years));
    const best = cars
      .filter((row) => row.age_years === oldest)
      .sort((a, b) => b.retained_value_pct - a.retained_value_pct)[0]!;
    show();
    const caption = section("valor-retenido").querySelector("figcaption")?.textContent ?? "";
    expect(caption).toContain(best.brand);
    expect(caption).toContain(`a los ${oldest} años`);
  });

  it("come with a hidden table of every value under each chart", () => {
    const { container } = show();
    // Hidden through a wrapper: `sr-only` on the table itself does not shrink it, and its
    // full width scrolled the page sideways on a phone.
    expect(container.querySelectorAll("table.sr-only")).toHaveLength(0);
    for (const id of ["depreciacion", "valor-retenido", "kilometraje", "regiones"]) {
      expect(section(id).querySelector(".sr-only table tbody tr")).not.toBeNull();
      expect(section(id).querySelector("figcaption.sr-only")?.textContent).not.toBe("");
    }
  });
});
