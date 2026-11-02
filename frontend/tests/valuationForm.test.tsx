import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "@/components/LanguageProvider";
import { ValuationForm } from "@/components/ValuationForm";
import type { CatalogResponse, ExplainResponse, PredictResponse } from "@/lib/api";

const catalog: CatalogResponse = {
  verticals: [
    {
      vehicle_type: "car",
      model_version: "2026-10-25.12948",
      train_rows: 6754,
      total_rows: 8443,
      trained_on_rows: 6754,
      brands: [
        {
          name: "Toyota",
          listings: 900,
          display_name: "Toyota",
          models: [{ name: "corolla", listings: 120, display_name: "Corolla" }],
        },
      ],
      departments: [{ name: "Bogotá D.C.", listings: 3000 }],
      model_year: { min: 1955, max: 2027 },
      engine_cc: { min: 800, max: 6400 },
      asking_price_cop: { min: 5_000_000, max: 400_000_000 },
    },
    {
      vehicle_type: "motorcycle",
      model_version: "2026-10-25.12948",
      train_rows: 2590,
      total_rows: 4505,
      trained_on_rows: 2590,
      brands: [{ name: "Bajaj", listings: 400, models: [] }],
      departments: [{ name: "Bogotá D.C.", listings: 1200 }],
      model_year: { min: 1958, max: 2027 },
      engine_cc: { min: 50, max: 2491 },
      asking_price_cop: { min: 900_000, max: 90_000_000 },
    },
  ],
};

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
  factors: [],
  model_version: "2026-10-25.12948",
};

/** One handler for all three endpoints, routed by path. */
function stubFetch() {
  const json = (body: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/catalog")) return json(catalog);
    if (url.endsWith("/predict")) return json(prediction);
    if (url.endsWith("/explain")) return json(explanation);
    return Promise.reject(new Error(`unexpected request to ${url}`));
  });
}

function show() {
  return render(
    <LanguageProvider>
      <ValuationForm />
    </LanguageProvider>,
  );
}

/** The catalogue has to land before the form is usable. */
const ready = () => waitFor(() => expect(screen.getByText("Modelo listo")).toBeInTheDocument());

/**
 * Find the priced-vehicle line by its mileage.
 *
 * A matcher function rather than a regex because `kilometres` joins the figure to its unit
 * with a non-breaking space on purpose — so that a figure never wraps away from its unit —
 * and a plain `/60\.000 km/` does not match one.
 */
const mileageLine = (text: string) => (_: string, element: Element | null) =>
  // Narrowed to the paragraph itself: every ancestor also contains the line, and matching
  // those would make the query ambiguous rather than wrong.
  element?.tagName === "P" && (element.textContent?.replace(/\s/g, " ").includes(text) ?? false);

/**
 * Pick an option out of a combobox.
 *
 * `mouseDown`, not `click`: the list commits on mousedown so that the choice registers
 * before `blur` closes the list out from under the pointer.
 */
async function choose(field: RegExp, query: string, option: RegExp) {
  const input = screen.getByLabelText(field);
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: query } });
  fireEvent.mouseDown(await screen.findByRole("option", { name: option }));
}

/**
 * Switch the site to English the way the header does.
 *
 * The toggle itself lives in `SiteChrome`, which this test does not render, so the change
 * goes through the store the provider actually listens to: `localStorage` plus the
 * `storage` event it subscribes to for cross-tab switching.
 */
function switchToEnglish() {
  act(() => {
    window.localStorage.setItem("autovalor.lang", "en");
    window.dispatchEvent(new StorageEvent("storage", { key: "autovalor.lang" }));
  });
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("fetch", stubFetch());
  // The focus move is scheduled on the next frame, so the frame has to actually run.
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 0;
  });
});

describe("submitting an incomplete form", () => {
  it("moves focus to the first field with a problem", async () => {
    // Focus used to stay on the button, with the make and year errors off-screen, so the
    // form looked like it had silently refused.
    show();
    await ready();

    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));

    await waitFor(() => expect(document.activeElement?.id).toBe("brand"));
  });

  it("brings that field into view", async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(this);
    };

    show();
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));

    await waitFor(() => expect(scrolled.map((node) => node.id)).toContain("brand"));
  });

  it("goes to the year once the make is answered", async () => {
    // Proves the order is the form's reading order rather than a hardcoded field.
    show();
    await ready();

    await choose(/Marca/, "Toyota", /Toyota/);

    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("year"));
  });

  it("does not submit", async () => {
    show();
    await ready();
    const calls = () =>
      vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/predict"));

    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("brand"));
    expect(calls()).toHaveLength(0);
  });
});

describe("the year field", () => {
  it("shows a year unseparated", async () => {
    show();
    await ready();
    const year = screen.getByLabelText(/Año del modelo/) as HTMLInputElement;

    fireEvent.change(year, { target: { value: "2024" } });

    // The reported bug rendered this as "2.024".
    expect(year.value).toBe("2024");
  });

  it("shows a year unseparated for a motorcycle too", async () => {
    // Asked for explicitly. It is the same field in both verticals -- switching vertical
    // keeps the year on purpose -- so this guards against that ever being two fields.
    show();
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Moto" }));

    const year = screen.getByLabelText(/Año del modelo/) as HTMLInputElement;
    fireEvent.change(year, { target: { value: "2024" } });

    expect(year.value).toBe("2024");
  });
});

describe("the priced-vehicle line", () => {
  /** Fill in every required field and submit. */
  async function priceACar() {
    show();
    await ready();

    await choose(/Marca/, "Toyota", /Toyota/);
    fireEvent.change(screen.getByLabelText(/Año del modelo/), { target: { value: "2018" } });
    fireEvent.change(screen.getByLabelText(/Kilometraje/), { target: { value: "60000" } });
    await choose(/Departamento/, "Bogot", /Bogot/);

    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
    await waitFor(() => expect(screen.getByText(mileageLine("60.000 km"))).toBeInTheDocument());
  }

  it("follows the language after the valuation, not the one it was priced in", async () => {
    // It used to be formatted once at submit time and kept as a string, so switching to
    // English left "60.000 km" sitting under English copy.
    await priceACar();

    switchToEnglish();

    await waitFor(() => expect(screen.getByText(mileageLine("60,000 km"))).toBeInTheDocument());
    expect(screen.queryByText(mileageLine("60.000 km"))).toBeNull();
  });
});

describe("a department the capture has not reached", () => {
  it("explains why nothing matched instead of quoting the query back", async () => {
    show();
    await ready();

    const input = screen.getByLabelText(/Departamento/);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "nari" } });

    expect(
      await screen.findByText("Todavía no tenemos anuncios suficientes de ese departamento."),
    ).toBeInTheDocument();
  });

  it("still offers another department when the filter matched nothing", async () => {
    // The escape hatch used to be filtered out along with everything else, so the one
    // person the message was written for had no way to act on it.
    show();
    await ready();

    const input = screen.getByLabelText(/Departamento/);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "nari" } });

    expect(await screen.findByRole("option", { name: /Otro departamento/ })).toBeInTheDocument();
  });

  it("says what it will do once that is chosen", async () => {
    show();
    await ready();
    await choose(/Departamento/, "nari", /Otro departamento/);

    expect(
      await screen.findByText("Usaremos el promedio de los departamentos que sí tenemos."),
    ).toBeInTheDocument();
  });
});

describe("the asking price floor", () => {
  it("rejects a price under the floor the service enforces", async () => {
    // 59 pesos used to be sent and come back labelled a bargain.
    show();
    await ready();

    const field = screen.getByLabelText(/Precio pedido/);
    fireEvent.change(field, { target: { value: "59" } });
    fireEvent.blur(field);

    expect(await screen.findByText(/El precio más bajo que el modelo vio es/)).toBeInTheDocument();
  });

  it("accepts a price inside the published range", async () => {
    show();
    await ready();

    const field = screen.getByLabelText(/Precio pedido/);
    fireEvent.change(field, { target: { value: "60000000" } });
    fireEvent.blur(field);

    expect(screen.queryByText(/El precio más bajo que el modelo vio es/)).toBeNull();
  });

  it("does not submit while the price is under the floor", async () => {
    show();
    await ready();

    await choose(/Marca/, "Toyota", /Toyota/);
    fireEvent.change(screen.getByLabelText(/Año del modelo/), { target: { value: "2018" } });
    fireEvent.change(screen.getByLabelText(/Kilometraje/), { target: { value: "60000" } });
    await choose(/Departamento/, "Bogot", /Bogot/);
    fireEvent.change(screen.getByLabelText(/Precio pedido/), { target: { value: "59" } });

    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));

    await waitFor(() => expect(document.activeElement?.id).toBe("asking"));
    expect(
      vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/predict")),
    ).toHaveLength(0);
  });
});

describe("the displacement error", () => {
  it("groups its bounds the way the placeholder does", async () => {
    show();
    await ready();

    const field = screen.getByLabelText(/Cilindrada/);
    fireEvent.change(field, { target: { value: "50" } });
    fireEvent.blur(field);

    // "800-6.400" in both places, rather than a grouped placeholder and a bare 6400.
    expect(await screen.findByText(/6\.400 cc/)).toBeInTheDocument();
  });
});
