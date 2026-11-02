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

describe("the warning notices", () => {
  it("says the estimate is an average when the department is not covered", () => {
    show({ prediction: { ...prediction, warnings: ["department_not_covered"] } });
    expect(
      screen.getByText(
        "Tu departamento no está en los datos, así que el estimado usa el promedio de los departamentos que sí tenemos.",
      ),
    ).toBeInTheDocument();
  });

  it("says the make alone was used when the model is not covered", () => {
    show({ prediction: { ...prediction, warnings: ["model_not_covered"] } });
    expect(
      screen.getByText("No tenemos anuncios de ese modelo, así que lo valoramos solo con la marca."),
    ).toBeInTheDocument();
  });

  it("shows both when both apply", () => {
    show({
      prediction: {
        ...prediction,
        warnings: ["department_not_covered", "model_not_covered"],
      },
    });
    const list = screen.getByRole("list", { name: "Avisos sobre este estimado" });
    expect(list.querySelectorAll("li")).toHaveLength(2);
  });

  it("says nothing when there is nothing to warn about", () => {
    show();
    expect(screen.queryByRole("list", { name: "Avisos sobre este estimado" })).toBeNull();
  });

  it("stays silent on a service that sends no warnings field at all", () => {
    const { warnings: _omitted, ...withoutField } = { ...prediction, warnings: [] };
    show({ prediction: withoutField as typeof prediction });
    expect(screen.queryByRole("list", { name: "Avisos sobre este estimado" })).toBeNull();
  });

  it("ignores a code this build does not know rather than printing it", () => {
    // The service can add a code before the site is rebuilt, and an untranslated
    // identifier on the page is worse than silence.
    show({
      prediction: {
        ...prediction,
        warnings: ["something_new_entirely"] as unknown as typeof prediction.warnings,
      },
    });
    expect(screen.queryByRole("list", { name: "Avisos sobre este estimado" })).toBeNull();
    expect(document.body.textContent).not.toContain("something_new_entirely");
  });
});
