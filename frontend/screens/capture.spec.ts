import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test, type Page } from "@playwright/test";

import {
  carCatalog,
  DEPARTMENT,
  estimate,
  MAKE,
  openValorar,
  remember,
  requireListed,
  settle,
} from "../e2e/helpers";

/**
 * Every view in every theme at every width, named `<view>_<theme>_<width>.jpg`.
 *
 * "auto-claro" and "auto-oscuro" are the Auto preference with the system in light and in
 * dark: the same pixels as Claro and Oscuro when Auto works, which is the point of having
 * them. The whole set goes to `screens-out/`; with `SCREENS_SELECTION=1` the subset the
 * README and the design notes use is also copied to `docs/design/screens/`.
 */

const OUT = path.resolve(process.env.SCREENS_DIR ?? "screens-out");
const SELECTED = path.resolve("..", "docs", "design", "screens");
const WIDTHS = [1440, 768, 375, 320] as const;
const THEMES = {
  claro: { pref: "light", system: "light" },
  oscuro: { pref: "dark", system: "dark" },
  "auto-claro": { pref: "auto", system: "light" },
  "auto-oscuro": { pref: "auto", system: "dark" },
} as const;
type ThemeName = keyof typeof THEMES;

const VIEWS = {
  "valorar-vacio": async (page: Page) => openValorar(page),
  "valorar-resultado": async (page: Page) => {
    await requireListed(page.request);
    const { model_year } = await carCatalog(page.request);
    const query = new URLSearchParams({
      tipo: "carro",
      marca: MAKE,
      // A recent car reads as a realistic example: the mid-point of 1955–2027 is 1991.
      anio: String(Math.round(model_year.max) - 8),
      km: "60000",
      depto: DEPARTMENT,
      precio: "60000000",
    });
    await page.goto(`/?${query}`);
    await estimate(page);
  },
  mercado: async (page: Page) => void (await page.goto("/mercado/")),
  metodologia: async (page: Page) => void (await page.goto("/metodologia/")),
  "404": async (page: Page) => void (await page.goto("/esta-pagina-no-existe/")),
} as const;

/** Each page at 1440 and 375 in Claro and Oscuro: the set kept in the repository. */
function selected(theme: ThemeName, width: number): boolean {
  return (theme === "claro" || theme === "oscuro") && (width === 1440 || width === 375);
}

/** The views the README shows, one screenful each. */
const README = new Set(["valorar-resultado", "mercado", "metodologia"]);

mkdirSync(OUT, { recursive: true });

for (const [view, open] of Object.entries(VIEWS)) {
  for (const [theme, { pref, system }] of Object.entries(THEMES) as [ThemeName, (typeof THEMES)[ThemeName]][]) {
    test.describe(() => {
      test.use({ colorScheme: system });
      for (const width of WIDTHS) {
        test(`${view}_${theme}_${width}`, async ({ page }) => {
          await remember(page, { theme: pref });
          await page.setViewportSize({ width, height: width < 640 ? 800 : 900 });
          await open(page);
          await settle(page);
          const name = `${view}_${theme}_${width}.jpg`;
          // The README shows one screen, not a page eight thousand pixels tall: the first
          // screenful at 1440, Valorar scrolled to its form and result. Taken before the
          // full-page capture, which leaves a sticky header drawn out of place.
          if (process.env.SCREENS_SELECTION === "1" && width === 1440 && README.has(view) && selected(theme, width)) {
            if (view === "valorar-resultado") {
              await page.locator("form").first().evaluate((node) => {
                // The site scrolls smoothly; a capture mid-scroll catches the header in motion.
                window.scrollTo({ top: node.getBoundingClientRect().top + window.scrollY - 80, behavior: "instant" });
              });
              await settle(page);
            }
            const screen = await page.screenshot({ type: "jpeg", quality: 80 });
            writeFileSync(path.join(SELECTED, `readme_${view}_${theme}.jpg`), screen);
            await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
            await settle(page);
          }
          const shot = await page.screenshot({ fullPage: true, type: "jpeg", quality: 72 });
          writeFileSync(path.join(OUT, name), shot);
          if (process.env.SCREENS_SELECTION === "1" && selected(theme, width)) {
            writeFileSync(path.join(SELECTED, name), shot);
          }
        });
      }
    });
  }
}
