/**
 * A valuation as a query string, so it survives a reload and can be shared.
 *
 * Only what the form asks for: the vehicle and, if typed, the asking price. Nothing about
 * the person, and nothing the API computes, so a link always re-runs the current model
 * instead of replaying an old answer. Short Spanish keys because the link is read by
 * people pasting it into a chat, and the site's default language is Spanish.
 */

import type { PredictRequest, VehicleType } from "./api";

const KEYS = {
  vehicle: "tipo",
  brand: "marca",
  model: "modelo",
  year: "anio",
  mileage: "km",
  department: "depto",
  engine: "cc",
  price: "precio",
} as const;

const VEHICLES: Record<string, VehicleType> = { carro: "car", moto: "motorcycle" };
const VEHICLE_SLUG: Record<VehicleType, string> = { car: "carro", motorcycle: "moto" };

export function toQuery(request: PredictRequest): string {
  const params = new URLSearchParams();
  params.set(KEYS.vehicle, VEHICLE_SLUG[request.vehicle_type]);
  params.set(KEYS.brand, request.brand);
  if (request.model) params.set(KEYS.model, request.model);
  params.set(KEYS.year, String(request.model_year));
  params.set(KEYS.mileage, String(request.mileage_km));
  params.set(KEYS.department, request.department);
  if (request.engine_cc != null) params.set(KEYS.engine, String(request.engine_cc));
  if (request.asking_price_cop != null) params.set(KEYS.price, String(request.asking_price_cop));
  return `?${params.toString()}`;
}

/** A whole, non-negative number, or undefined: a link is typed by people as well. */
function count(value: string | null): number | undefined {
  if (value === null || !/^\d{1,12}$/.test(value)) return undefined;
  return Number(value);
}

/**
 * Read a valuation back, or null when the link does not carry a complete one.
 *
 * Only the shape is checked here; whether the make or the department exists is the
 * catalogue's call, made by the form against the lists it loaded.
 */
export function fromQuery(search: string): PredictRequest | null {
  const params = new URLSearchParams(search);
  const vehicle = VEHICLES[params.get(KEYS.vehicle) ?? ""];
  const brand = params.get(KEYS.brand)?.trim();
  const department = params.get(KEYS.department)?.trim();
  const year = count(params.get(KEYS.year));
  const mileage = count(params.get(KEYS.mileage));
  if (!vehicle || !brand || !department || year === undefined || mileage === undefined) {
    return null;
  }
  return {
    vehicle_type: vehicle,
    brand,
    model: params.get(KEYS.model)?.trim() || null,
    model_year: year,
    mileage_km: mileage,
    department,
    engine_cc: count(params.get(KEYS.engine)) ?? null,
    asking_price_cop: count(params.get(KEYS.price)) ?? null,
  };
}
