import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:8000";
export const PAGES = ["/", "/mercado/", "/metodologia/"] as const;

type Range = { min: number; max: number };
export type Catalog = {
  vehicle_type: string;
  brands: { name: string }[];
  departments: { name: string }[];
  model_year: Range;
  engine_cc: Range | null;
  asking_price_cop: Range | null;
  mileage_km?: Range | null;
};

/** The car catalogue the service publishes, which every expected limit is read from. */
export async function carCatalog(request: APIRequestContext): Promise<Catalog> {
  const response = await request.get(`${API}/catalog`);
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { verticals: Catalog[] };
  const car = body.verticals.find((vertical) => vertical.vehicle_type === "car");
  if (!car) throw new Error("no car catalogue");
  return car;
}

/** Remember a language and a theme before the first paint, as a returning visitor would. */
export async function remember(page: Page, prefs: { lang?: "es" | "en"; theme?: string }) {
  await page.addInitScript((values) => {
    if (values.lang) window.localStorage.setItem("autovalor.lang", values.lang);
    if (values.theme) window.localStorage.setItem("autovalor.theme", values.theme);
  }, prefs);
}

/** Open Valorar and wait for /catalog, which is what puts the ranges in the placeholders. */
export async function openValorar(page: Page) {
  await page.goto("/");
  await expect(page.locator("#year")).toHaveAttribute("placeholder", /\d{4}–\d{4}/);
}

/** Type into a combobox and pick the option that appears. */
export async function choose(page: Page, id: string, typed: string, option: RegExp) {
  const input = page.locator(`#${id}`);
  await input.click();
  await input.fill(typed);
  await page.getByRole("option", { name: option }).first().click();
}

/** The make and department the valuation cases use; a test skips if either disappears. */
export const MAKE = "Toyota";
export const DEPARTMENT = "Antioquia";

/** Skip, saying why, when the catalogue no longer lists the make or department used here. */
export async function requireListed(request: APIRequestContext) {
  const car = await carCatalog(request);
  test.skip(!car.brands.some((brand) => brand.name === MAKE), `/catalog no longer lists ${MAKE}`);
  test.skip(
    !car.departments.some((department) => department.name === DEPARTMENT),
    `/catalog no longer lists ${DEPARTMENT}`,
  );
}

/**
 * A year inside the published range, read from the field's placeholder ("1955–2027"),
 * which the form fills from /catalog. Never a literal: the top year moves every January.
 */
export async function validYear(page: Page): Promise<string> {
  const placeholder = (await page.locator("#year").getAttribute("placeholder")) ?? "";
  const [min, max] = placeholder.split("–").map(Number);
  if (!min || !max) throw new Error(`no year range in the placeholder: "${placeholder}"`);
  return String(Math.floor((min + max) / 2));
}

/** A complete, valid car, so a test only changes the field it is about. */
export async function fillCar(page: Page) {
  await requireListed(page.request);
  await choose(page, "brand", MAKE, new RegExp(`^${MAKE}`));
  await page.locator("#year").fill(await validYear(page));
  await page.locator("#mileage").fill("60000");
  await choose(page, "department", DEPARTMENT, new RegExp(`^${DEPARTMENT}`));
}

export function submit(page: Page) {
  return page.getByRole("button", { name: /^(Calcular el precio|Estimate the price)$/ }).click();
}

/** The estimate as printed, in full pesos, once the result has arrived. */
export async function estimate(page: Page): Promise<string> {
  const value = page.locator('section[aria-labelledby="result-title"] dd small').first();
  await expect(value).toBeVisible({ timeout: 30_000 });
  return (await value.textContent()) ?? "";
}

/** Count the /predict calls a page makes from here on. */
export function countPredictions(page: Page): () => number {
  let calls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/predict")) calls += 1;
  });
  return () => calls;
}

/** The relative luminance of the body's background, whatever colour space CSS gave it. */
export function bodyLuminance(page: Page): Promise<number> {
  return page.evaluate(() => {
    const colour = getComputedStyle(document.body).backgroundColor;
    // A canvas normalises lab(), oklch() and rgb() alike into sRGB bytes.
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const context = canvas.getContext("2d")!;
    context.fillStyle = colour;
    context.fillRect(0, 0, 1, 1);
    const [r, g, b] = [...context.getImageData(0, 0, 1, 1).data].map((byte) => {
      const c = byte / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
  });
}

/**
 * Wait for what moves measurements: web fonts, transitions still running (a toggle caught
 * half-way through its colour change reads as low contrast) and charts that draw once at
 * a fallback width before measuring their box.
 */
export async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    document
            .getAnimations()
            .every((animation) => !(animation instanceof CSSTransition) || animation.playState !== "running"),
  );
  await page.waitForFunction(() =>
    [...document.querySelectorAll<SVGSVGElement>("svg[viewBox]")].every((svg) => {
      const width = svg.viewBox.baseVal.width;
      return width === 0 || svg.clientWidth === 0 || Math.abs(svg.clientWidth - width) < 2;
    }),
  );
}
