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
import { resetBrands } from "@/lib/brandSelection";
import { MAX_COMPARED } from "@/lib/market";
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

/** The "Reading" card of a section, which lives inside the active tab panel. */
function reading(id: string): string {
  return section(id).querySelector("[data-reading] p:last-child")?.textContent ?? "";
}

function chip(name: string): HTMLElement {
  return within(section("valor-retenido")).getByRole("button", { name: new RegExp(`^${name}`) });
}

/** Makes drawn in colour on the retained-value chart, in slot order. */
function coloured(): string[] {
  return [...section("valor-retenido").querySelectorAll("svg g[data-curve]")].map(
    (node) => node.getAttribute("data-curve") ?? "",
  );
}

beforeEach(() => {
  // The choice lives in memory as well as in storage, so a test that picked motorcycles
  // would otherwise leave the next one on them.
  chooseVehicle("car");
  resetBrands();
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
    // The motorcycle reading names the thin departments in its few-listings note, so the
    // check is on the extremes sentence: the cheapest region it quotes is a covered one.
    const covered = regional
      .filter((row) => row.vehicle_type === "motorcycle" && !isThin(row.listings))
      .sort((a, b) => a.pct_change - b.pct_change);
    show();
    chooseMotorcycles("regiones");
    const text = reading("regiones");
    expect(text).toContain(`por debajo en ${covered[0]!.department}`);
    for (const row of thinMoto) expect(text).not.toContain(`por debajo en ${row.department}`);
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

  it("never prints the old 'pct · age' legend", () => {
    show();
    expect(screen.queryByText(/% · \d+$/)).toBeNull();
  });
});

const carsAtOldest = (() => {
  const cars = retainedValue().filter((row) => row.vehicle_type === "car");
  const oldest = Math.max(...cars.map((row) => row.age_years));
  return cars
    .filter((row) => row.age_years === oldest)
    .sort((a, b) => b.retained_value_pct - a.retained_value_pct);
})();

describe("comparing makes on the retained-value chart", () => {
  const reference = depreciation().find((row) => row.vehicle_type === "car" && row.is_reference)!;
  const defaults = [
    ...new Set([carsAtOldest[0]!.brand, carsAtOldest.at(-1)!.brand, reference.brand]),
  ];

  it("opens with the make that keeps most, the one that keeps least and the reference", () => {
    show();
    expect(coloured()).toEqual(defaults);
    for (const brand of defaults) expect(chip(brand)).toHaveAttribute("aria-pressed", "true");
  });

  it("offers every make as a chip, with what it keeps", () => {
    show();
    for (const row of carsAtOldest) {
      expect(chip(row.brand).textContent).toContain(percent(row.retained_value_pct, "es", 0));
    }
  });

  it("keeps the makes nobody picked as background lines", () => {
    show();
    const background = section("valor-retenido").querySelectorAll("polyline[data-background]");
    expect(background).toHaveLength(carsAtOldest.length - defaults.length);
  });

  it("adds and removes a make", () => {
    show();
    const extra = carsAtOldest.find((row) => !defaults.includes(row.brand))!.brand;
    act(() => fireEvent.click(chip(extra)));
    expect(coloured()).toEqual([...defaults, extra]);
    expect(reading("valor-retenido")).toContain(extra);
    act(() => fireEvent.click(chip(extra)));
    expect(coloured()).toEqual(defaults);
  });

  it(`stops at ${MAX_COMPARED} and says why`, () => {
    show();
    for (const row of carsAtOldest) {
      const button = chip(row.brand);
      if (button.getAttribute("aria-pressed") === "false" && !button.hasAttribute("disabled")) {
        act(() => fireEvent.click(button));
      }
    }
    expect(coloured()).toHaveLength(MAX_COMPARED);
    const free = carsAtOldest.filter((row) => !coloured().includes(row.brand));
    for (const row of free) expect(chip(row.brand)).toBeDisabled();
    expect(section("valor-retenido").textContent).toContain(
      `Llegaste a ${MAX_COMPARED} marcas`,
    );
  });

  it("counts every tap when several land before a re-render", () => {
    show();
    const free = carsAtOldest.filter((row) => !defaults.includes(row.brand)).map((row) => row.brand);
    const buttons = free.slice(0, MAX_COMPARED - defaults.length).map(chip);
    // One act for all of them: React renders once at the end, as with quick taps.
    act(() => buttons.forEach((button) => fireEvent.click(button)));
    expect(coloured()).toHaveLength(MAX_COMPARED);
  });

  it("clears and resets", () => {
    show();
    act(() => fireEvent.click(within(section("valor-retenido")).getByRole("button", { name: "Quitar todas" })));
    expect(coloured()).toEqual([]);
    expect(reading("valor-retenido")).toContain(copy.market.retained.compareNone.es);
    act(() => fireEvent.click(within(section("valor-retenido")).getByRole("button", { name: "Restablecer" })));
    expect(coloured()).toEqual(defaults);
  });

  it("remembers each vertical's choice apart", () => {
    const first = show();
    act(() => fireEvent.click(within(section("valor-retenido")).getByRole("button", { name: "Quitar todas" })));
    chooseMotorcycles("valor-retenido");
    const motoChoice = coloured();
    expect(motoChoice.length).toBeGreaterThan(0);
    first.unmount();
    show();
    // Still on motorcycles from the shared tab choice: their defaults survived the car clear.
    expect(coloured()).toEqual(motoChoice);
    act(() => {
      fireEvent.click(within(section("valor-retenido")).getByRole("tab", { name: copy.form.cars.es }));
    });
    expect(coloured()).toEqual([]);
  });

  it("flags a make whose depreciation is indistinguishable from zero", () => {
    const flat = depreciation().filter((row) => row.vehicle_type === "motorcycle" && !row.significant);
    expect(flat.length).toBeGreaterThan(0);
    show();
    chooseMotorcycles("valor-retenido");
    for (const row of flat) {
      expect(chip(row.brand).textContent).toContain(copy.market.notSignificant.es);
    }
  });
});

describe("readings follow the tab", () => {
  const fastest = (vertical: "car" | "motorcycle") =>
    depreciation()
      .filter((row) => row.vehicle_type === vertical && row.significant)
      .sort((a, b) => b.annual_depreciation_pct - a.annual_depreciation_pct)[0]!.brand;

  it("talks about cars on the car tab and motorcycles on the motorcycle tab", () => {
    show();
    const car = reading("depreciacion");
    expect(car).toContain(fastest("car"));
    expect(car).not.toContain(fastest("motorcycle"));
    chooseMotorcycles("depreciacion");
    const moto = reading("depreciacion");
    expect(moto).toContain(fastest("motorcycle"));
    expect(moto).not.toBe(car);
  });

  it("switches every tabbed section's reading", () => {
    show();
    const ids = ["depreciacion", "valor-retenido", "kilometraje", "regiones"];
    const before = ids.map(reading);
    chooseMotorcycles("kilometraje");
    ids.forEach((id, index) => {
      expect(reading(id)).not.toBe("");
      expect(reading(id)).not.toBe(before[index]);
    });
  });

  it("names the thin departments on the motorcycle regional reading", () => {
    show();
    chooseMotorcycles("regiones");
    for (const row of thinMoto) expect(reading("regiones")).toContain(row.department);
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
    expect(caption.toLowerCase()).toContain(`a los ${oldest} años`);
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
