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
      mileage_km: { min: 0, max: 2_000_000 },
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
      mileage_km: { min: 0, max: 1_500_000 },
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
    Promise.resolve({ ok: true, status: 200, headers: new Headers(), json: () => Promise.resolve(body) } as Response);
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
  // A priced valuation writes itself into the address bar, and a page that opens on such
  // an address prices it again: each test starts from a clean one.
  window.history.replaceState(null, "", "/");
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

describe("the shareable link", () => {
  const predictCalls = () =>
    vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/predict"));

  async function priceToyota() {
    await choose(/Marca/, "Toyota", /Toyota/);
    fireEvent.change(screen.getByLabelText(/Año del modelo/), { target: { value: "2018" } });
    fireEvent.change(screen.getByLabelText(/Kilometraje/), { target: { value: "60000" } });
    await choose(/Departamento/, "Bogot", /Bogot/);
    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
    await screen.findByRole("button", { name: "Copiar enlace" });
  }

  it("writes the priced request into the address bar", async () => {
    show();
    await ready();
    await priceToyota();
    const params = new URLSearchParams(window.location.search);
    expect(params.get("tipo")).toBe("carro");
    expect(params.get("marca")).toBe("Toyota");
    expect(params.get("anio")).toBe("2018");
    expect(params.get("km")).toBe("60000");
    expect(params.get("depto")).toBe("Bogotá D.C.");
  });

  it("prices a shared link on arrival, with the form filled in", async () => {
    window.history.replaceState(
      null,
      "",
      "/?tipo=carro&marca=Toyota&modelo=corolla&anio=2019&km=45000&depto=Bogot%C3%A1+D.C.",
    );
    show();
    await waitFor(() => expect(predictCalls()).toHaveLength(1));
    const body = JSON.parse(String(predictCalls()[0]?.[1]?.body));
    expect(body).toMatchObject({ brand: "Toyota", model: "corolla", model_year: 2019, mileage_km: 45000 });
    expect(screen.getByLabelText(/Año del modelo/)).toHaveValue("2019");
  });

  it("ignores a link to a make the catalogue does not have", async () => {
    window.history.replaceState(null, "", "/?tipo=carro&marca=Lada&anio=2019&km=1&depto=Meta");
    show();
    await ready();
    expect(predictCalls()).toHaveLength(0);
  });

  it("clears the address bar on 'Valorar otro'", async () => {
    show();
    await ready();
    await priceToyota();
    fireEvent.click(screen.getByRole("button", { name: "Valorar otro" }));
    expect(window.location.search).toBe("");
  });
});

describe("the waking notice", () => {
  it("also explains a valuation that takes more than five seconds", async () => {
    const base = stubFetch();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).endsWith("/predict") || String(input).endsWith("/explain")
          ? new Promise<Response>(() => {})
          : base(input),
      ),
    );
    show();
    await ready();
    await choose(/Marca/, "Toyota", /Toyota/);
    fireEvent.change(screen.getByLabelText(/Año del modelo/), { target: { value: "2018" } });
    fireEvent.change(screen.getByLabelText(/Kilometraje/), { target: { value: "60000" } });
    await choose(/Departamento/, "Bogot", /Bogot/);
    // Fake time only from here: the combobox helpers wait on real timers.
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
      act(() => vi.advanceTimersByTime(4_000));
      expect(screen.queryByText("El servicio está arrancando")).toBeNull();
      act(() => vi.advanceTimersByTime(1_500));
      expect(screen.getByText("El servicio está arrancando")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the field groups", () => {
  it("keeps the odometer with the vehicle and the listing to department and price", async () => {
    show();
    await ready();
    const vehicle = screen.getByRole("group", { name: "El vehículo" });
    const listing = screen.getByRole("group", { name: "El anuncio" });
    for (const label of [/Marca/, /Año del modelo/, /Kilometraje/, /Cilindrada/]) {
      expect(vehicle.contains(screen.getByLabelText(label))).toBe(true);
    }
    for (const label of [/Departamento/, /Precio pedido/]) {
      expect(listing.contains(screen.getByLabelText(label))).toBe(true);
    }
  });
});

describe("the field ranges", () => {
  /** What the screen reader hears under a field besides its label, by the field's label. */
  const describedText = (label: RegExp) => {
    const input = screen.getByLabelText(label);
    const ids = (input.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
    return ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
  };

  it("live in the placeholder only, with no hint under any field", async () => {
    show();
    await ready();
    expect(screen.getByLabelText(/Año del modelo/)).toHaveAttribute("placeholder", "1955–2027");
    expect(screen.getByLabelText(/Kilometraje/)).toHaveAttribute("placeholder", "0–2.000.000");
    expect(screen.getByLabelText(/Cilindrada/)).toHaveAttribute("placeholder", "800–6.400");
    expect(screen.getByLabelText(/Precio pedido/)).toHaveAttribute("placeholder", "5.000.000");
    for (const label of [/Año del modelo/, /Kilometraje/, /Cilindrada/, /Precio pedido/, /Modelo/]) {
      expect(describedText(label)).toBe("");
    }
    for (const retired of [
      /valoramos con la marca/,
      /^Entre \d/,
      /^Hasta \d/,
      /déjala vacía/,
      /Si lo escribes, lo comparamos/,
    ]) {
      expect(screen.queryByText(retired)).toBeNull();
    }
  });

  it("follow the vehicle type", async () => {
    show();
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Moto" }));
    expect(screen.getByLabelText(/Año del modelo/)).toHaveAttribute("placeholder", "1958–2027");
    expect(screen.getByLabelText(/Kilometraje/)).toHaveAttribute("placeholder", "0–1.500.000");
    expect(screen.getByLabelText(/Cilindrada/)).toHaveAttribute("placeholder", "50–2.491");
  });

  it("refuse a 1930 car when the field is left", async () => {
    show();
    await ready();
    const year = screen.getByLabelText(/Año del modelo/);
    fireEvent.change(year, { target: { value: "1930" } });
    fireEvent.blur(year);
    expect(screen.getByText("El año tiene que estar entre 1955 y 2027.")).toBeInTheDocument();
    expect(year).toHaveAttribute("aria-invalid", "true");
  });

  it("refuse a 1930 car on submit, without calling the service", async () => {
    show();
    await ready();
    await choose(/Marca/, "Toyota", /Toyota/);
    fireEvent.change(screen.getByLabelText(/Año del modelo/), { target: { value: "1930" } });
    fireEvent.change(screen.getByLabelText(/Kilometraje/), { target: { value: "60000" } });
    await choose(/Departamento/, "Bogot", /Bogot/);
    fireEvent.click(screen.getByRole("button", { name: "Calcular el precio" }));
    expect(screen.getByText("El año tiene que estar entre 1955 y 2027.")).toBeInTheDocument();
    const predicted = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).endsWith("/predict"));
    expect(predicted).toHaveLength(0);
  });

  it("share their range with the placeholder and the error message", async () => {
    show();
    await ready();
    const year = screen.getByLabelText(/Año del modelo/);
    expect(year).toHaveAttribute("placeholder", "1955–2027");
    fireEvent.change(year, { target: { value: "1900" } });
    fireEvent.blur(year);
    expect(screen.getByText("El año tiene que estar entre 1955 y 2027.")).toBeInTheDocument();

    const km = screen.getByLabelText(/Kilometraje/);
    expect(km).toHaveAttribute("placeholder", "0–2.000.000");
    fireEvent.change(km, { target: { value: "2000001" } });
    fireEvent.blur(km);
    expect(screen.getByText("Escribe un kilometraje entre 0 y 2.000.000 km.")).toBeInTheDocument();
  });

  it("show no odometer limit when the service does not publish one", async () => {
    const withoutMileage: CatalogResponse = {
      verticals: catalog.verticals.map(({ mileage_km: _drop, ...rest }) => rest),
    };
    const base = stubFetch();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).endsWith("/catalog")
          ? Promise.resolve({ ok: true, status: 200, headers: new Headers(), json: () => Promise.resolve(withoutMileage) } as Response)
          : base(input),
      ),
    );
    show();
    await ready();
    expect(screen.getByLabelText(/Kilometraje/)).not.toHaveAttribute("placeholder");
    const km = screen.getByLabelText(/Kilometraje/);
    fireEvent.change(km, { target: { value: "9000000" } });
    fireEvent.blur(km);
    expect(screen.queryByText(/Escribe un kilometraje entre/)).toBeNull();
  });
});

describe("lists answered from the service worker's saved copy", () => {
  it("say they are saved and may be out of date, instead of 'Modelo listo'", async () => {
    const base = stubFetch();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).endsWith("/catalog")
          ? Promise.resolve({
              ok: true,
              status: 200,
              headers: new Headers({ "x-autovalor-cached-at": "2026-11-01T10:00:00.000Z" }),
              json: () => Promise.resolve(catalog),
            } as Response)
          : base(input),
      ),
    );
    show();
    // Not `ready()`: that waits for the very "Modelo listo" this case replaces.
    expect(
      await screen.findByText(/^Sin conexión: listas guardadas el 1 de noviembre de 2026/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Modelo listo")).toBeNull();
  });
});
