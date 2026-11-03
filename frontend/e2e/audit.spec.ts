import { expect, test, type Page } from "@playwright/test";

import { audit } from "./audit";
import { carCatalog, DEPARTMENT, estimate, MAKE, remember, requireListed, settle } from "./helpers";

/**
 * Legibility, contrast, overflow and target size on every page, theme and width.
 *
 * Valorar is audited with a result on screen, since the result card carries most of the
 * small print; it gets there through a shared link, which runs the valuation on load.
 */

// 640 is the first `sm` width, where the bars and the figure column first share a row.
const WIDTHS = [1440, 768, 640, 375, 320] as const;
const THEMES = ["light", "dark"] as const;
const ROUTES = ["valorar", "/mercado/", "/metodologia/", "/esta-pagina-no-existe/"] as const;

async function open(page: Page, route: (typeof ROUTES)[number]) {
  if (route !== "valorar") {
    await page.goto(route);
    return;
  }
  await requireListed(page.request);
  const { model_year } = await carCatalog(page.request);
  const year = Math.floor((model_year.min + model_year.max) / 2);
  const query = new URLSearchParams({
    tipo: "carro",
    marca: MAKE,
    anio: String(year),
    km: "60000",
    depto: DEPARTMENT,
    precio: "60000000",
  });
  await page.goto(`/?${query}`);
  await estimate(page);
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    for (const route of ROUTES) {
      test(`${route} · ${theme} · ${width}px`, async ({ page }) => {
        await remember(page, { theme });
        await page.setViewportSize({ width, height: 900 });
        await open(page, route);
        await settle(page);
        const violations = await page.evaluate(audit, { mobile: width < 640 });
        expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
      });
    }
  }
}
