import { expect, test } from "@playwright/test";

import { audit } from "./audit";

/**
 * The audit, run on a page built to break every rule once. A checker that finds nothing
 * on the real site is only evidence if it finds these.
 */
const BROKEN = `
  <body style="margin:0;background:#ffffff;font:16px sans-serif">
    <p style="font-size:11px;color:#111">Too small</p>
    <p style="color:#aaaaaa">Too faint</p>
    <p style="color:lab(20% 0 0)">Dark lab() text that passes</p>
    <p style="color:oklch(0.85 0 0)">Light oklch() text that fails</p>
    <div style="background-image:linear-gradient(red,blue)"><p style="color:#000">On a gradient</p></div>
    <svg width="200" height="20" viewBox="0 0 200 20">
      <line x1="0" x2="200" y1="10" y2="10" stroke="#dddddd" stroke-width="2" />
    </svg>
    <input placeholder="ok" style="border:1px solid #eeeeee;color:#000" />
    <button style="width:30px;height:30px">x</button>
    <a href="#" style="display:block;height:16px;font-size:14px;color:#000">Short link</a>
    <div style="width:2000px;height:10px"></div>
  </body>`;

test("every rule fires on a page made to break it", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.setContent(BROKEN);
  const found = await page.evaluate(audit, { mobile: true });
  const rules = (where: RegExp) => found.filter((v) => where.test(v.where)).map((v) => v.rule);

  expect(rules(/^p "Too small/)).toContain("text-size");
  expect(rules(/^p "Too faint/)).toContain("text-contrast");
  expect(rules(/^p "Dark lab/)).toEqual([]);
  expect(rules(/^p "Light oklch/)).toContain("text-contrast");
  // A colour that cannot be reduced to one value is a failure, never a pass.
  expect(found.find((v) => /On a gradient/.test(v.where))?.detail).toMatch(/background-image/);
  expect(found.some((v) => v.rule === "graphic-contrast" && v.where.startsWith("svg"))).toBe(true);
  expect(found.some((v) => v.rule === "control-border")).toBe(true);
  expect(rules(/button "x"/)).toContain("touch-target");
  expect(rules(/Short link/)).toContain("touch-target");
  expect(found.some((v) => v.rule === "horizontal-scroll")).toBe(true);
});

test("desktop asks 24 px of links and nothing of buttons", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 800 });
  await page.setContent(BROKEN);
  const found = await page.evaluate(audit, { mobile: false });
  expect(found.filter((v) => /Short link/.test(v.where)).map((v) => v.rule)).toContain("link-target");
  expect(found.some((v) => /button "x"/.test(v.where))).toBe(false);
});
