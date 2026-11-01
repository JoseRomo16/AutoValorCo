import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { PriceResult } from "@/components/PriceResult";
import type { ExplainResponse, PredictResponse } from "@/lib/api";

/**
 * The figures of the audit's worked example, so the assertions read against something
 * that was actually observed rather than round numbers invented here.
 */
const prediction: PredictResponse = {
  vehicle_type: "car",
  band: {
    lower_cop: 70_000_000,
    estimate_cop: 73_000_000,
    upper_cop: 132_000_000,
    relative_width: 0.85,
  },
  label: "fair",
  precision_notice: null,
  model_version: "2026-10-25.12948",
};

const explanation: ExplainResponse = {
  vehicle_type: "car",
  estimate_cop: 73_000_000,
  base_price_cop: 60_000_000,
  factors: [
    {
      feature: "model_year",
      label: { es: "Año del modelo", en: "Model year" },
      value: "2018",
      value_display: { es: "2018", en: "2018" },
      factor: 1.12,
      direction: "raises",
    },
  ],
  model_version: "2026-10-25.12948",
};

function show(overrides: Partial<Parameters<typeof PriceResult>[0]> = {}) {
  return render(
    <LanguageProvider>
      <PriceResult
        prediction={prediction}
        explanation={explanation}
        askingPrice={null}
        spec={null}
        busy={false}
        {...overrides}
      />
    </LanguageProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("the screen-reader announcement", () => {
  it("announces a summary, not the whole card", () => {
    show();
    // The live region is the only thing with aria-live, and it holds one sentence.
    const live = document.querySelectorAll("[aria-live]");
    expect(live).toHaveLength(1);
    expect(live[0]?.textContent).toBe(
      "Precio estimado: $ 73 millones. Rango: $ 70 millones a $ 132 millones. Etiqueta: Justo.",
    );
  });

  it("does not make the panel itself a live region", () => {
    // The whole result used to be aria-live, so all five factors were read out on arrival
    // before the listener could reach the price.
    show();
    const panel = screen.getByRole("region");
    expect(panel).not.toHaveAttribute("aria-live");
  });

  it("says so when no label was published", () => {
    show({ prediction: { ...prediction, label: null, precision_notice: "too wide" } });
    expect(document.querySelector("[aria-live]")?.textContent).toContain("Sin etiqueta.");
  });

  it("keeps the live region mounted before the first valuation", () => {
    // A region created at the same moment as its text is often missed, so it has to exist
    // in the empty state too.
    show({ prediction: null, explanation: null });
    expect(document.querySelectorAll("[aria-live]")).toHaveLength(1);
  });
});

describe("the range bar", () => {
  it("has a text equivalent instead of being hidden", () => {
    show();
    const bar = screen.getByRole("img");
    expect(bar).toHaveAttribute(
      "aria-label",
      "Rango: P10 $ 70 millones, estimado $ 73 millones, P90 $ 132 millones.",
    );
  });

  it("includes the asking price when there is one", () => {
    show({ askingPrice: 80_000_000 });
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Precio pedido:");
  });

  it("leaves the asking price out when there is none", () => {
    show();
    expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("Precio pedido:");
  });
});

describe("what must not be said", () => {
  it("offers no explanation of where the estimate sits in the range", () => {
    // Deliberate: the estimate landing near a bound is a model problem (Block 4), and the
    // "log asymmetry" story is false — a log-symmetric range would put the estimate at the
    // geometric centre, about 96 millones here, not 73.
    show();
    const text = document.body.textContent ?? "";
    for (const forbidden of ["asimetr", "logar", "log-", "geométric", "cerca del P10"]) {
      expect(text.toLowerCase()).not.toContain(forbidden.toLowerCase());
    }
  });
});
