import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { Methodology } from "@/components/Methodology";
import { decimal, isoDay, percent } from "@/lib/format";
import { copy, fill } from "@/lib/i18n";
import { isThin } from "@/lib/listings";
import { featureCoverage, labelGate, manifest, segmentError, servedModels } from "@/lib/results";

/**
 * The methodology page on the committed bundles and results, the files the static export
 * reads. Expectations come from those files, so a retrain moves them with the page.
 */

const models = servedModels();
const car = models.find((model) => model.vehicle_type === "car")!;
const moto = models.find((model) => model.vehicle_type === "motorcycle")!;
const results = manifest();

function show() {
  return render(
    <LanguageProvider>
      <Methodology
        models={models}
        manifest={results}
        segments={segmentError()}
        gate={labelGate()}
        coverage={featureCoverage()}
      />
    </LanguageProvider>,
  );
}

const text = () => document.body.textContent ?? "";

beforeEach(() => window.localStorage.clear());

describe("the published error (ADR 0006, c)", () => {
  it("shows the random partition as the headline and the temporal one beside it", () => {
    expect(car.temporal).not.toBeNull();
    show();
    const section = document.getElementById("resultados")!;
    const table = within(section).getByRole("table", { name: copy.method.results.errorsCaption.es });
    expect(table.textContent).toContain(percent(car.mape * 100, "es"));
    expect(table.textContent).toContain(percent(car.temporal!.mape * 100, "es"));
    expect(table.textContent).toContain(percent(moto.temporal!.mape * 100, "es"));
  });

  it("defines both and states the span of the captures", () => {
    show();
    expect(text()).toContain("Partición aleatoria:");
    expect(text()).toContain("En anuncios más nuevos que los datos de entrenamiento:");
    expect(text()).toContain(`${decimal(car.temporal!.span_days, "es")} días`);
  });
});

describe("data and privacy", () => {
  it("says the capture is paused, with the last capture's date, and never 'once a week'", () => {
    show();
    const last = results.capture_dates.at(-1)!;
    expect(document.getElementById("datos")!.textContent).toContain(isoDay(last, "es"));
    expect(text()).not.toMatch(/una vez por semana/i);
  });
});

describe("terms", () => {
  it.each([
    copy.terms.averageError,
    copy.terms.range,
    copy.terms.calibration,
    copy.terms.heldOut,
    copy.terms.shap,
  ])("defines $term.es where it first appears", (entry) => {
    show();
    const button = screen.getAllByRole("button", { name: entry.term.es })[0]!;
    act(() => fireEvent.focus(button));
    const tip = document.getElementById(button.getAttribute("aria-describedby")!)!;
    expect(tip.textContent).toBe(entry.definition.es);
    expect(tip.className).toContain("block");
  });
});

describe("table of contents", () => {
  it("links every section, on desktop and in the folding version for phones", () => {
    const { container } = show();
    const desktop = within(screen.getByRole("navigation")).getAllByRole("link");
    expect(desktop.length).toBe(6);
    for (const link of desktop) {
      expect(document.getElementById(link.getAttribute("href")!.slice(1))).not.toBeNull();
    }
    expect(container.querySelector("details summary")?.textContent).toBe(copy.method.toc.label.es);
    expect(desktop[0]).toHaveAttribute("aria-current", "true");
  });
});

describe("scope", () => {
  it("quotes the displacement coverage from make results, per vehicle type", () => {
    const share = (vertical: string) =>
      featureCoverage().find((row) => row.vehicle_type === vertical && row.feature === "engine_cc")!
        .coverage_pct;
    show();
    const section = document.getElementById("alcance")!;
    expect(section.textContent).toContain(
      fill(copy.method.scope.items.engineWhat, "es", {
        car: percent(share("car"), "es"),
        moto: percent(share("motorcycle"), "es"),
      }),
    );
  });

  it("lists every covered department and names the thin ones", () => {
    show();
    const scope = document.getElementById("alcance")!.textContent ?? "";
    const all = new Set(models.flatMap((model) => model.departments.map((d) => d.name)));
    for (const name of all) expect(scope).toContain(name);
    expect(scope).toContain(copy.method.scope.items.otherWhat.es);
    expect(scope).toContain(copy.method.scope.items.cityWhat.es);
    expect(scope).toContain(copy.method.scope.items.unknownModelWhat.es);
    const thin = models.flatMap((m) => m.departments.filter((d) => isThin(d.listings)).map((d) => d.name));
    expect(thin.length).toBeGreaterThan(0);
  });
});

describe("the label rule", () => {
  it("badges each vertical as the bundle decides", () => {
    show();
    const rule = document.getElementById("etiqueta")!;
    for (const model of models) {
      const name = model.vehicle_type === "car" ? copy.form.cars.es : copy.form.motorcycles.es;
      const card = within(rule).getByRole("heading", { name }).parentElement!.parentElement!;
      expect(card.textContent).toContain(
        model.publishes_label ? copy.method.results.published.es : copy.method.results.withheld.es,
      );
    }
  });
});
