import { expect, test, type Page } from "@playwright/test";

import { copy } from "../lib/i18n";
import { PAGES, remember } from "./helpers";

/**
 * The site-wide behaviour the redesign promised: the header, the phone toggles, language
 * and theme that survive navigation without a flash, short transitions that stop for
 * reduced motion, and a visible focus ring on everything a keyboard reaches.
 */

test.describe("the header", () => {
  test("is sticky, compact, translucent, blurred and gains a fine line on scroll", async ({ page }) => {
    await page.goto("/metodologia/");
    const header = page.locator("header").first();
    const before = await header.evaluate((node) => {
      const style = getComputedStyle(node);
      return {
        position: style.position,
        top: style.top,
        height: node.getBoundingClientRect().height,
        blur: style.backdropFilter,
        background: style.backgroundColor,
      };
    });
    expect(before.position).toBe("sticky");
    expect(before.top).toBe("0px");
    expect(before.height).toBeLessThanOrEqual(72);
    expect(before.blur).toMatch(/blur\(\d/);
    const alpha = await page.evaluate((colour) => {
      const canvas = document.createElement("canvas").getContext("2d")!;
      canvas.fillStyle = colour;
      canvas.fillRect(0, 0, 1, 1);
      return canvas.getImageData(0, 0, 1, 1).data[3]! / 255;
    }, before.background);
    expect(alpha, "translucent background").toBeGreaterThan(0.5);
    expect(alpha, "translucent background").toBeLessThan(1);

    await page.mouse.wheel(0, 800);
    await expect
      .poll(() => header.evaluate((node) => getComputedStyle(node).borderBottomColor))
      .not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
    const line = await header.evaluate((node) => parseFloat(getComputedStyle(node).borderBottomWidth));
    expect(line).toBeGreaterThan(0);
    expect(line).toBeLessThanOrEqual(1);
    expect(await header.evaluate((node) => node.getBoundingClientRect().top)).toBe(0);
  });

  test("on a phone, the navigation and both toggles are readable and 44 px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: copy.nav.settings.es }).click();
    const controls = page.locator(
      `header nav a, [role=group][aria-label="${copy.lang.label.es}"] button, [role=group][aria-label="${copy.theme.label.es}"] button`,
    );
    expect(await controls.count()).toBeGreaterThanOrEqual(8);
    for (const control of await controls.all()) {
      const box = (await control.boundingBox())!;
      expect(box.height, await control.innerText()).toBeGreaterThanOrEqual(44);
      expect(box.width, await control.innerText()).toBeGreaterThanOrEqual(44);
      const size = await control.evaluate((node) => parseFloat(getComputedStyle(node).fontSize));
      expect(size, await control.innerText()).toBeGreaterThanOrEqual(13);
    }
  });
});

/** Record what each of the first frames painted, before and through hydration. */
async function recordFrames(page: Page) {
  await page.addInitScript(() => {
    const frames: { theme?: string; lang: string; text: string; hidden: boolean }[] = [];
    (window as unknown as { __frames: typeof frames }).__frames = frames;
    const log = () => {
      const root = document.documentElement;
      frames.push({
        theme: root.dataset.theme,
        lang: root.lang,
        text: document.querySelector("h1")?.textContent ?? "",
        hidden: document.body ? getComputedStyle(document.body).visibility === "hidden" : true,
      });
      // Until the page has been visible for a few frames, bounded by LANG_SCRIPT's 3 s
      // release: a slow runner must not turn a late hydration into "never shown".
      const visible = frames.filter((frame) => !frame.hidden).length;
      if (visible < 5 && frames.length < 600) requestAnimationFrame(log);
      else (window as unknown as { __framesDone: boolean }).__framesDone = true;
    };
    requestAnimationFrame(log);
  });
}

test("language and theme are remembered across pages and never flash", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await page.getByRole("button", { name: copy.theme.dark.en, exact: true }).click();
  await recordFrames(page);

  for (const route of ["/mercado/", "/metodologia/", "/"]) {
    await page.goto(route);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.waitForFunction(() => (window as unknown as { __framesDone?: boolean }).__framesDone === true);
    const frames = await page.evaluate(
      () => (window as unknown as { __frames: { theme?: string; text: string; hidden: boolean }[] }).__frames,
    );
    for (const frame of frames) {
      expect(frame.theme, `${route}: every painted frame is dark`).toBe("dark");
    }
    // A frame either shows nothing yet or shows English: never the Spanish export.
    const shown = frames.filter((frame) => !frame.hidden);
    expect(shown.length, `${route}: the page does appear`).toBeGreaterThan(0);
    const heading = await page.locator("h1").first().innerText();
    for (const frame of shown) expect(frame.text.trim(), route).toBe(heading.trim());
  }
});

test.describe("motion", () => {
  /** Every running transition duration on the page, in milliseconds, without zeros. */
  const durations = (page: Page) =>
    page.evaluate(() => {
      const found = new Set<number>();
      for (const element of document.querySelectorAll("*")) {
        for (const part of getComputedStyle(element).transitionDuration.split(",")) {
          const ms = parseFloat(part) * (part.trim().endsWith("ms") ? 1 : 1000);
          if (ms > 0) found.add(Math.round(ms * 100) / 100);
        }
      }
      return [...found];
    });

  for (const route of PAGES) {
    test(`${route} transitions last 150–250 ms`, async ({ page }) => {
      await page.goto(route);
      const found = await durations(page);
      expect(found.length).toBeGreaterThan(0);
      for (const ms of found) {
        expect(ms).toBeGreaterThanOrEqual(150);
        expect(ms).toBeLessThanOrEqual(250);
      }
    });
  }

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });
    for (const route of PAGES) {
      test(`${route} has no transition longer than a frame`, async ({ page }) => {
        await page.goto(route);
        for (const ms of await durations(page)) expect(ms).toBeLessThan(1);
        expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe(
          "auto",
        );
      });
    }
  });
});

for (const theme of ["light", "dark"] as const) {
  test(`every control reached by Tab shows a visible outline (${theme})`, async ({ page }) => {
    test.setTimeout(120_000);
    await remember(page, { theme });
    for (const route of PAGES) {
      await page.goto(route);
      const seen = new Set<string>();
      for (let step = 0; step < 60; step += 1) {
        await page.keyboard.press("Tab");
        // transition-colors animates outline-color too; measure the ring once it has landed.
        await page.waitForFunction(() =>
          document
            .getAnimations()
            .every((animation) => !(animation instanceof CSSTransition) || animation.playState !== "running"),
        );
        const ring = await page.evaluate(() => {
          const element = document.activeElement as HTMLElement | null;
          if (!element || element === document.body) return null;
          const style = getComputedStyle(element);
          const key = `${element.tagName}#${element.id}.${(element.textContent ?? "").trim().slice(0, 30)}`;
          // The outline against the ground behind it, through a canvas like the audit.
          const canvas = document.createElement("canvas").getContext("2d")!;
          const rgb = (colour: string) => {
            canvas.clearRect(0, 0, 1, 1);
            canvas.fillStyle = colour;
            canvas.fillRect(0, 0, 1, 1);
            return [...canvas.getImageData(0, 0, 1, 1).data.slice(0, 3)];
          };
          const lum = (c: number[]) =>
            c
              .map((v) => v / 255)
              .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
              .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i]!, 0);
          let ground = "rgb(255,255,255)";
          for (let node: Element | null = element.parentElement; node; node = node.parentElement) {
            const bg = getComputedStyle(node).backgroundColor;
            if (bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") {
              ground = bg;
              break;
            }
          }
          const [a, b] = [lum(rgb(style.outlineColor)), lum(rgb(ground))].sort((x, y) => y - x);
          return {
            key,
            style: style.outlineStyle,
            width: parseFloat(style.outlineWidth),
            contrast: (a! + 0.05) / (b! + 0.05),
          };
        });
        if (!ring || seen.has(ring.key)) continue;
        seen.add(ring.key);
        expect(ring.style, `${route} ${ring.key}`).not.toBe("none");
        expect(ring.width, `${route} ${ring.key}`).toBeGreaterThanOrEqual(2);
        expect(ring.contrast, `${route} ${ring.key}`).toBeGreaterThanOrEqual(3);
      }
      expect(seen.size, `${route}: Tab reaches controls`).toBeGreaterThan(5);
    }
  });
}
