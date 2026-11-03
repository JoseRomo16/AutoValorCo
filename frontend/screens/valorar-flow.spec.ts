import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test } from "@playwright/test";

import { choose, DEPARTMENT, estimate, MAKE, openValorar, requireListed, settle } from "../e2e/helpers";

/**
 * The frames of the README's Valorar GIF: pick a make, type the year and mileage, pick a
 * department, price it. Only with `VALORAR_GIF=1`; `scripts/valorar_gif.py` turns the
 * frames into `docs/design/valorar.gif`.
 */
test.skip(process.env.VALORAR_GIF !== "1", "set VALORAR_GIF=1 to record the GIF frames");

const FRAMES = path.resolve(process.env.SCREENS_DIR ?? "screens-out", "valorar-flow");

test("valorar flow", async ({ page }) => {
  test.setTimeout(120_000);
  mkdirSync(FRAMES, { recursive: true });
  await page.setViewportSize({ width: 1100, height: 760 });
  await requireListed(page.request);
  await openValorar(page);
  await settle(page);
  let index = 0;
  const shot = async (holds = 1) => {
    const image = await page.screenshot({ type: "png" });
    for (let i = 0; i < holds; i += 1) {
      writeFileSync(path.join(FRAMES, `${String(index).padStart(4, "0")}.png`), image);
      index += 1;
    }
  };
  const type = async (id: string, text: string) => {
    await page.locator(`#${id}`).click();
    for (const character of text) {
      await page.keyboard.type(character);
      await shot();
    }
  };

  await shot(6);
  await type("brand", MAKE.slice(0, 4));
  await choose(page, "brand", MAKE, new RegExp(`^${MAKE}`));
  await shot(3);
  // A recent car reads as a realistic example; the top of the range comes from /catalog.
  const placeholder = (await page.locator("#year").getAttribute("placeholder")) ?? "";
  const top = Number(placeholder.split("–")[1]);
  await type("year", String(top - 8));
  await type("mileage", "60000");
  await shot(2);
  await type("department", DEPARTMENT.slice(0, 4));
  await page.getByRole("option", { name: new RegExp(`^${DEPARTMENT}`) }).first().click();
  await shot(3);
  await page.getByRole("button", { name: "Calcular el precio" }).click();
  await estimate(page);
  await settle(page);
  await page.locator('section[aria-labelledby="result-title"]').scrollIntoViewIfNeeded();
  await shot(14);
});
