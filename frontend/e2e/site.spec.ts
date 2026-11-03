import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { copy } from "../lib/i18n";
import { LINKEDIN_URL } from "../lib/links";
import { bodyLuminance, estimate, fillCar, openValorar, PAGES, remember, submit } from "./helpers";

type Leaf = { es: string; en: string };

/** Every Spanish string the site can print that its English version does not share. */
function spanishOnly(node: unknown): string[] {
  if (node === null || typeof node !== "object") return [];
  const record = node as Record<string, unknown>;
  if (typeof record.es === "string" && typeof record.en === "string") {
    const { es, en } = record as Leaf;
    if (es === en) return [];
    // A template is checked by its literal pieces, since the slots are filled with data.
    return es
      .split(/\{\w+\}/)
      .map((piece) => piece.trim())
      .filter((piece) => piece.length >= 12 && !en.includes(piece));
  }
  return Object.values(record).flatMap(spanishOnly);
}

const SPANISH = [...new Set(spanishOnly(copy))];

/** A number grouped the Spanish way, "1.600" or "45.000.000", not part of a version tag. */
const SPANISH_NUMBER = /(?<![\d.-])\d{1,3}(?:\.\d{3})+(?!\d)/;

test.describe("in English", () => {
  test.beforeEach(async ({ page }) => remember(page, { lang: "en" }));

  for (const route of PAGES) {
    test(`${route} keeps no Spanish in the tab title, the text or the numbers`, async ({ page }) => {
      if (route === "/") {
        await openValorar(page);
        await fillCar(page);
        await page.locator("#asking").fill("45000000");
        await submit(page);
        await estimate(page);
      } else {
        await page.goto(route);
      }
      await expect(page).toHaveTitle(/AutoValor CO/);
      const title = await page.title();
      for (const localized of Object.values(copy.titles)) {
        if (localized.es !== localized.en) expect(title).not.toContain(localized.es);
      }

      const text = await page.locator("body").innerText();
      const leftovers = SPANISH.filter((piece) => text.includes(piece));
      expect(leftovers, "Spanish strings on the English page").toEqual([]);
      expect(text.match(SPANISH_NUMBER)?.[0] ?? null, "a number grouped the Spanish way").toBeNull();
      expect(text).toMatch(/\d,\d{3}/);
    });
  }
});

test("an unknown URL shows the site's own 404 in the active theme", async ({ page }) => {
  await remember(page, { theme: "dark" });
  const response = await page.goto("/esta-pagina-no-existe/");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: copy.notFound.title.es })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await bodyLuminance(page)).toBeLessThan(0.1);
});

test("og:image is a 1200×630 PNG that the build wrote", async ({ page }) => {
  await page.goto("/");
  const image = await page.locator('meta[property="og:image"]').getAttribute("content");
  expect(image).toMatch(/\/og\.png$/);
  await expect(page.locator('meta[property="og:image:width"]')).toHaveAttribute("content", "1200");
  await expect(page.locator('meta[property="og:image:height"]')).toHaveAttribute("content", "630");

  const file = readFileSync(path.join(process.cwd(), "out", new URL(image!).pathname));
  // The PNG signature, then the IHDR chunk's width and height, big-endian.
  expect(file.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect([file.readUInt32BE(16), file.readUInt32BE(20)]).toEqual([1200, 630]);
});

test("every LinkedIn link on the site points at the same profile", async ({ page }) => {
  const found = new Set<string>();
  for (const route of [...PAGES, "/esta-pagina-no-existe/"]) {
    await page.goto(route);
    const hrefs = await page
      .locator('a[href*="linkedin.com"]')
      .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
    expect(hrefs.length, `${route} links to LinkedIn`).toBeGreaterThan(0);
    hrefs.forEach((href) => found.add(href));
  }
  expect([...found]).toEqual([LINKEDIN_URL]);
});

test.describe("the Auto theme with a dark system", () => {
  test.use({ colorScheme: "dark" });

  for (const route of PAGES) {
    test(`${route} paints the dark theme`, async ({ page }) => {
      await remember(page, { theme: "auto" });
      await page.goto(route);
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
      await expect(page.locator("html")).toHaveAttribute("data-theme-pref", "auto");
      expect(await bodyLuminance(page)).toBeLessThan(0.1);
    });
  }
});
