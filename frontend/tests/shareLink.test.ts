import { describe, expect, it } from "vitest";

import type { PredictRequest } from "@/lib/api";
import { fromQuery, toQuery } from "@/lib/shareLink";

const full: PredictRequest = {
  vehicle_type: "motorcycle",
  brand: "BMW",
  model: "r 1250 gs",
  model_year: 2021,
  mileage_km: 18000,
  department: "Bogotá D.C.",
  engine_cc: 1254,
  asking_price_cop: 89000000,
};

describe("share link", () => {
  it("round-trips a full valuation", () => {
    expect(fromQuery(toQuery(full))).toEqual(full);
  });

  it("round-trips one without the optional fields", () => {
    const bare: PredictRequest = {
      ...full,
      vehicle_type: "car",
      model: null,
      engine_cc: null,
      asking_price_cop: null,
    };
    const query = toQuery(bare);
    expect(query).not.toContain("modelo=");
    expect(query).not.toContain("precio=");
    expect(fromQuery(query)).toEqual(bare);
  });

  it("uses short Spanish keys and readable values", () => {
    expect(toQuery(full)).toContain("tipo=moto");
    expect(toQuery(full)).toContain("marca=BMW");
  });

  it.each([
    ["no vehicle", "?marca=BMW&anio=2021&km=1&depto=Meta"],
    ["an unknown vehicle", "?tipo=bus&marca=BMW&anio=2021&km=1&depto=Meta"],
    ["no make", "?tipo=carro&anio=2021&km=1&depto=Meta"],
    ["a year that is not a number", "?tipo=carro&marca=Kia&anio=dos&km=1&depto=Meta"],
    ["a negative mileage", "?tipo=carro&marca=Kia&anio=2021&km=-5&depto=Meta"],
    ["no department", "?tipo=carro&marca=Kia&anio=2021&km=1"],
  ])("refuses a link with %s", (_case, query) => {
    expect(fromQuery(query)).toBeNull();
  });

  it("drops a malformed optional field instead of the whole link", () => {
    const parsed = fromQuery("?tipo=carro&marca=Kia&anio=2021&km=1000&depto=Meta&precio=mucho");
    expect(parsed?.asking_price_cop).toBeNull();
  });
});
