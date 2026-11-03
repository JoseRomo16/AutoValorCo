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
      anio: String(Math.floor((model_year.min + model_year.max) / 2)),
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
