import { expect, test } from "@playwright/test";

import { copy, fill } from "../lib/i18n";
import {
  carCatalog,
  choose,
  countPredictions,
  estimate,
  fillToyota,
  openValorar,
  submit,
} from "./helpers";

test("a typed year reads 2024, without a thousands separator", async ({ page }) => {
  await openValorar(page);
  await page.locator("#year").pressSequentially("2024");
  await expect(page.locator("#year")).toHaveValue("2024");
});

test("a price with junk says what it dropped, and one under the floor is refused", async ({
  page,
  request,
}) => {
  const floor = Math.floor((await carCatalog(request)).asking_price_cop!.min);
  const predictions = countPredictions(page);
  await openValorar(page);
  await fillToyota(page);
  const asking = page.locator("#asking");
  await asking.focus();
  // As one input event, the way it arrives when pasted. Typed key by key, each keystroke
  // reports only what it dropped, so the notice clears when the next digit lands.
  await page.keyboard.insertText("-5e9");
  await expect(page.getByText(fill(copy.form.discarded, "es", { chars: "-e" }))).toBeVisible();
  await expect(asking).toHaveValue("59");
  expect(59).toBeLessThan(floor);

  await asking.blur();
  await expect(page.getByText(/^El precio más bajo que el modelo vio es /)).toBeVisible();
  await submit(page);
  await expect(asking).toBeFocused();
  expect(predictions()).toBe(0);
});

test("a pasted 45.000.000,00 is 45 million, not 4.500 million", async ({ page }) => {
  await openValorar(page);
  await fillToyota(page);
  await page.locator("#asking").focus();
  // One input event carrying the whole string, which is what a paste is.
  await page.keyboard.insertText("45.000.000,00");
  await expect(page.locator("#asking")).toHaveValue("45.000.000");

  const sent = page.waitForRequest((call) => call.url().endsWith("/predict"));
  await submit(page);
  expect((await sent).postDataJSON().asking_price_cop).toBe(45_000_000);
});

test("a year outside /catalog shows the inline error with the published range", async ({
  page,
  request,
}) => {
  const { min, max } = (await carCatalog(request)).model_year;
  await openValorar(page);
  const year = page.locator("#year");
  await year.fill(String(Math.round(min) - 1));
  await year.blur();
  await expect(
    page.getByText(fill(copy.form.errors.year, "es", { min: Math.round(min), max: Math.round(max) })),
  ).toBeVisible();
  await expect(year).toHaveAttribute("aria-invalid", "true");
});

test("an uncovered department offers another department and the result says it averaged", async ({
  page,
}) => {
  await openValorar(page);
  await choose(page, "brand", "Toyota", /^Toyota/);
  await page.locator("#year").fill("2018");
  await page.locator("#mileage").fill("60000");
  await page.locator("#department").click();
  await page.locator("#department").fill("nari");
  await expect(page.getByText(copy.form.departmentNoMatch.es)).toBeVisible();
  await page.getByRole("option", { name: new RegExp(`^${copy.form.departmentOther.es}`) }).click();
  await submit(page);
  await estimate(page);
  await expect(page.getByText(copy.result.warnings.departmentNotCovered.es)).toBeVisible();
});

test("an empty submit puts the focus on the first field in error", async ({ page }) => {
  const predictions = countPredictions(page);
  await openValorar(page);
  await submit(page);
  await expect(page.locator("#brand")).toBeFocused();
  await expect(page.getByText(copy.form.errors.brand.es)).toBeVisible();
  expect(predictions()).toBe(0);
});

test("the shareable link re-runs the same valuation", async ({ page, context }) => {
  await openValorar(page);
  await fillToyota(page);
  await submit(page);
  const first = await estimate(page);
  await expect(page).toHaveURL(/\?.*marca=Toyota/);

  const shared = await context.newPage();
  const recalculated = shared.waitForRequest((call) => call.url().endsWith("/predict"));
  await shared.goto(page.url());
  await recalculated;
  expect(await estimate(shared)).toBe(first);
});
