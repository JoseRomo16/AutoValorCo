/**
 * The typed client for the valuation API.
 *
 * These types are hand-written against the FastAPI contract rather than generated from
 * its OpenAPI document. The reason is the build: generating them would put a network call
 * to a sleeping free-tier service on the critical path of `npm run build`, and a frontend
 * that cannot be built offline is a frontend that cannot be built in CI. The payloads are
 * small and the contract has tests of its own on the Python side.
 *
 * Everything here runs in the browser. The static export has no server, so there is no
 * second place where a request could be made.
 */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://autovalor-api.onrender.com"
).replace(/\/$/, "");

export type VehicleType = "car" | "motorcycle";

/**
 * A level of a categorical feature, as the catalogue publishes it.
 *
 * `name` is what the model was trained on and what has to be sent back. `display_name` is
 * the same level spelled for a person: the lake stores `cx-30` and a reader expects
 * `CX-30`. It is optional because a deployed image older than the catalogue cleaning does
 * not send it, and the site has to work against either.
 */
export type CatalogEntry = { name: string; listings: number; display_name?: string };

export type CatalogBrand = {
  name: string;
  listings: number;
  display_name?: string;
  models: CatalogEntry[];
};

export type CatalogRange = { min: number; max: number };

export type VerticalCatalog = {
  vehicle_type: VehicleType;
  model_version: string;
  /** Listings the lists and the model were derived from. */
  train_rows: number;
  /** Listings in the lake before any split. Null on a service older than these names. */
  total_rows: number | null;
  /** @deprecated Equals `train_rows`; the service keeps sending it. Use `train_rows`. */
  trained_on_rows: number;
  brands: CatalogBrand[];
  departments: CatalogEntry[];
  /** What `/predict` accepts: the training span, capped at the current year plus one. */
  model_year: CatalogRange;
  engine_cc: CatalogRange | null;
  /**
   * Where an asking price may plausibly fall. Null on a bundle exported before the range
   * existed, which is what the deployed service serves until the next `make export-model`
   * -- so the form has to treat a missing range as "no floor to enforce".
   */
  asking_price_cop: CatalogRange | null;
  /**
   * The odometer range `/predict` accepts. Absent from a service deployed before it was
   * published, and then the form shows no limit and enforces none: the API still does.
   */
  mileage_km?: CatalogRange | null;
};

export type CatalogResponse = { verticals: VerticalCatalog[] };

export type PredictRequest = {
  vehicle_type: VehicleType;
  brand: string;
  model?: string | null;
  model_year: number;
  mileage_km: number;
  department: string;
  engine_cc?: number | null;
  asking_price_cop?: number | null;
};

export type PriceLabel = "bargain" | "fair" | "expensive";

/**
 * Why a label was withheld, as data.
 *
 * `message` is the service's own English sentence and `code` is what the site renders in
 * Spanish. Optional for the same reason as `display_name`: an older deployed image sends
 * only `precision_notice`, and the fallback is to say the range is not precise enough
 * without quoting figures the response did not carry.
 */
export type PrecisionCode = {
  code: string;
  value: number;
  limit: number;
  message: string;
};

/**
 * Something worth telling the reader about an answer that is still real.
 *
 * Not `precision_codes`, which explains a withheld label and carries a measured value and
 * limit. These say the model had less to go on than the caller supplied.
 */
export type Warning = "model_not_covered" | "department_not_covered";

export type PredictResponse = {
  vehicle_type: VehicleType;
  band: {
    lower_cop: number;
    estimate_cop: number;
    upper_cop: number;
    relative_width: number;
  };
  label: PriceLabel | null;
  precision_notice: string | null;
  precision_codes?: PrecisionCode[];
  /** Optional because a service older than this field sends none. */
  warnings?: Warning[];
  model_version: string;
};

export type LocalizedText = { es: string; en: string };

export type Factor = {
  feature: string;
  label: LocalizedText;
  value: string | null;
  value_display: LocalizedText;
  factor: number;
  direction: "raises" | "lowers";
  /** The value is one the service fixes (the form never asks), not one the caller typed.
   * Optional: an API deployed before Block 4 does not send it. */
  assumed?: boolean;
};

export type ExplainResponse = {
  vehicle_type: VehicleType;
  estimate_cop: number;
  base_price_cop: number;
  factors: Factor[];
  warnings?: Warning[];
  model_version: string;
};

/** Thrown with a message meant to be rendered, not logged. */
export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestWithHeaders<T>(path, init)).body;
}

async function requestWithHeaders<T>(
  path: string,
  init?: RequestInit,
): Promise<{ body: T; headers: Headers }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    // A cold start that exceeds the browser's patience, an offline client and a CORS
    // rejection all land here as the same opaque TypeError, so the message says what is
    // most likely and what to do rather than guessing at a cause it cannot see.
    throw new ApiError(String(cause));
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new ApiError(detail ?? `HTTP ${response.status}`);
  }
  return { body: (await response.json()) as T, headers: response.headers };
}

/**
 * The catalogue, and when it was saved if it did not come from the network.
 *
 * Offline, the service worker answers /catalog with the last copy that worked and stamps
 * it with `x-autovalor-cached-at` (ADR 0007), so the form can load and still say its
 * lists may be out of date. Online the header is absent and `cachedAt` is null.
 */
export async function fetchCatalog(): Promise<CatalogResponse & { cachedAt: string | null }> {
  const { body, headers } = await requestWithHeaders<CatalogResponse>("/catalog");
  return { ...body, cachedAt: headers.get("x-autovalor-cached-at") };
}

export function fetchPrediction(payload: PredictRequest): Promise<PredictResponse> {
  return request<PredictResponse>("/predict", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchExplanation(payload: PredictRequest): Promise<ExplainResponse> {
  return request<ExplainResponse>("/explain", { method: "POST", body: JSON.stringify(payload) });
}
