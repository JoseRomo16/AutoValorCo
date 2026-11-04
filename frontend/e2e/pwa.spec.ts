import { spawn, type ChildProcess } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { copy } from "../lib/i18n";
import { carCatalog, DEPARTMENT, MAKE, requireListed } from "./helpers";

/**
 * The installable app (ADR 0007): manifest and icons, the worker's strategies, offline
 * behaviour, the update notice after a new build, and the emergency worker.
 */

const OUT = path.resolve("out");

/** Wait until the page is controlled by an active worker, reloading once if needed. */
async function controlled(page: Page) {
  await page.evaluate(() => navigator.serviceWorker.ready);
  if (!(await page.evaluate(() => navigator.serviceWorker.controller !== null))) {
    await page.reload();
  }
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
}

/** The version the controlling worker reports. */
function version(page: Page) {
  return page.evaluate(
    () =>
      new Promise<string>((resolve) => {
        const channel = new MessageChannel();
        channel.port1.onmessage = (event) => resolve(String(event.data));
        navigator.serviceWorker.controller!.postMessage({ type: "GET_VERSION" }, [channel.port2]);
      }),
  );
}

test.describe("the manifest", () => {
  test("is valid, uses the stylesheet's ground and lists icons that exist", async ({ page, request }) => {
    const response = await request.get("/manifest.webmanifest");
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toContain("application/manifest+json");
    const manifest = await response.json();
    // The layout's dark theme-color is read from globals.css by the same helper the
    // manifest generator uses, so the two must agree, and neither is typed by hand.
    // Read from the HTML as built: in the browser ThemeProvider repaints the metas.
    void page;
    const html = await (await request.get("/")).text();
    const ground =
      html.match(/name="theme-color" content="(#[0-9a-f]{6})" media="\(prefers-color-scheme: dark\)"/i)?.[1] ??
      null;
    expect(ground).toMatch(/^#[0-9a-f]{6}$/i);
    const dark = { ground };
    expect(manifest).toMatchObject({
      name: "AutoValor CO",
      short_name: "AutoValor",
      start_url: "/",
      scope: "/",
      display: "standalone",
      lang: "es",
      theme_color: dark.ground,
      background_color: dark.ground,
    });
    expect(manifest.description.length).toBeGreaterThan(20);

    const purposes = new Set<string>();
    for (const icon of manifest.icons as { src: string; sizes: string; purpose: string }[]) {
      const file = await request.get(icon.src);
      expect(file.ok(), icon.src).toBe(true);
      const bytes = Buffer.from(await file.body());
      expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
      expect(`${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`).toBe(icon.sizes);
      purposes.add(icon.purpose);
    }
    expect([...purposes].sort()).toEqual(["any", "maskable"]);
    expect(manifest.icons.map((icon: { sizes: string }) => icon.sizes)).toEqual(
      expect.arrayContaining(["192x192", "512x512"]),
    );
  });

  test("is linked from every page with the iOS tags", async ({ page }) => {
    for (const route of ["/", "/mercado/", "/metodologia/"]) {
      await page.goto(route);
      await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
      await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
        "href",
        "/icons/apple-touch-icon.png",
      );
      // The favicon: an SVG first, a PNG for browsers without SVG favicons, both served.
      const icons = page.locator('link[rel="icon"]');
      await expect(icons.first()).toHaveAttribute("href", "/icon.svg");
      for (const href of await icons.evaluateAll((links) => links.map((l) => l.getAttribute("href")))) {
        const response = await page.request.get(href!);
        expect(response.ok(), href!).toBe(true);
        expect(response.headers()["content-type"]).toMatch(/^image\//);
      }
      await expect(page.locator('meta[name="apple-mobile-web-app-capable"], meta[name="mobile-web-app-capable"]').first()).toHaveAttribute("content", "yes");
      expect(await page.locator('meta[name="theme-color"]').count()).toBe(2);
    }
  });
});

test("the worker registers and controls the page", async ({ page }) => {
  await page.goto("/");
  await controlled(page);
  expect(await page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)).toMatch(/\/sw\.js$/);
  expect(await version(page)).toMatch(/^[0-9a-f]{12}$/);
});

test("only GET is intercepted, and of other origins only /catalog", async ({ page, request }) => {
  await requireListed(request);
  await page.goto("/");
  await controlled(page);

  const seen: { url: string; method: string; fromWorker: boolean }[] = [];
  page.on("response", (response) =>
    seen.push({
      url: response.url(),
      method: response.request().method(),
      fromWorker: response.fromServiceWorker(),
    }),
  );
  const { model_year } = await carCatalog(request);
  const query = new URLSearchParams({
    tipo: "carro",
    marca: MAKE,
    anio: String(Math.round(model_year.max) - 8),
    km: "60000",
    depto: DEPARTMENT,
  });
  await page.goto(`/?${query}`);
  await expect(page.locator('section[aria-labelledby="result-title"] dd small').first()).toBeVisible({
    timeout: 30_000,
  });
  await page.evaluate(() => fetch("http://localhost:8000/health").then((r) => r.status));

  const find = (pattern: RegExp, method = "GET") =>
    seen.find((entry) => pattern.test(entry.url) && entry.method === method);
  expect(find(/:8000\/predict$/, "POST")?.fromWorker).toBe(false);
  expect(find(/:8000\/explain$/, "POST")?.fromWorker).toBe(false);
  expect(find(/:8000\/health$/)?.fromWorker).toBe(false);
  expect(find(/:8000\/catalog$/)?.fromWorker).toBe(true);
  expect(find(/localhost:3000\/\?/)?.fromWorker).toBe(true);
});

test.describe("offline", () => {
  test("Market, Methodology, a shared Valorar link and an unsaved page", async ({ page, context, request }) => {
    await requireListed(request);
    // Online first: install the worker and let the form save /catalog once.
    await page.goto("/");
    await controlled(page);
    // The first load asks /catalog before the worker controls the page; the next one goes
    // through it, which is when the fallback copy is saved (ADR 0007).
    await page.reload();
    await expect(page.getByText(copy.status.ready.es)).toBeVisible({ timeout: 30_000 });

    await context.setOffline(true);

    await page.goto("/mercado/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Qué dice el mercado/);
    await page.goto("/metodologia/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // A shared link carries a query string the cache never saw: matched ignoring it.
    const { model_year } = await carCatalog(request);
    const query = new URLSearchParams({
      tipo: "carro",
      marca: MAKE,
      anio: String(Math.round(model_year.max) - 8),
      km: "60000",
      depto: DEPARTMENT,
    });
    // Valorar loads its lists from the saved copy, and says they may be out of date.
    await page.goto("/");
    await expect(page.locator("#year")).toHaveAttribute("placeholder", /\d{4}–\d{4}/);
    await expect(page.getByText(/^Sin conexión: listas guardadas el /)).toBeVisible();

    await page.goto(`/?${query}`);
    await expect(page.locator("#year")).toHaveAttribute("placeholder", /\d{4}–\d{4}/);
    // The link re-runs the valuation, which needs the service: the offline message, not
    // the generic offline page.
    await expect(page.getByText(copy.result.errors.offlineTitle.es)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: copy.pwa.offline.title.es })).toHaveCount(0);

    await page.goto("/una-pagina-que-nunca-se-guardo/");
    await expect(page.getByRole("heading", { name: copy.pwa.offline.title.es })).toBeVisible();
    const offlinePages = page.getByRole("navigation", { name: copy.pwa.offline.pages.es });
    await expect(offlinePages.getByRole("link", { name: copy.nav.market.es })).toHaveAttribute("href", "/mercado/");
    await expect(offlinePages.getByRole("link", { name: copy.nav.method.es })).toHaveAttribute(
      "href",
      "/metodologia/",
    );

    await context.setOffline(false);
  });
});

/**
 * A second build, simulated: a copy of `out/` served on its own port, whose `sw.js` and
 * home page are then changed the way a deploy changes them.
 */
async function deployCopy(port: number) {
  const dir = mkdtempSync(path.join(tmpdir(), "autovalor-out-"));
  cpSync(OUT, dir, { recursive: true });
  const server: ChildProcess = spawn(process.execPath, ["e2e/serve.mjs", dir], {
    env: { ...process.env, PORT: String(port) },
    stdio: "ignore",
  });
  const base = `http://localhost:${port}`;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      if ((await fetch(base)).ok) break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  return {
    base,
    dir,
    /** A new build: a new worker version and a visible marker in the home page. */
    redeploy() {
      const sw = path.join(dir, "sw.js");
      writeFileSync(sw, readFileSync(sw, "utf-8").replace(/const VERSION = "([0-9a-f]+)"/, 'const VERSION = "$1-next"'));
      const home = path.join(dir, "index.html");
      writeFileSync(home, readFileSync(home, "utf-8").replace("<head>", '<head><meta name="build" content="next">'));
    },
    /** The emergency build: the kill worker, and pages that register nothing. */
    kill() {
      cpSync(path.resolve("scripts", "sw-kill.js"), path.join(dir, "sw.js"));
      for (const page of ["index.html", "mercado/index.html", "metodologia/index.html"]) {
        const file = path.join(dir, page);
        writeFileSync(
          file,
          readFileSync(file, "utf-8").replace('name="autovalor-sw" content="on"', 'name="autovalor-sw" content="off"'),
        );
      }
    },
    close() {
      server.kill();
      rmSync(dir, { recursive: true, force: true });
    },
  };
}

test.describe("after a deploy", () => {
  test("the update notice appears and loads the new version", async ({ page }) => {
    const site = await deployCopy(3101);
    try {
      await page.goto(`${site.base}/mercado/`);
      await controlled(page);
      const before = await version(page);

      site.redeploy();
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())!.update());
      await expect(page.getByText(copy.pwa.updateReady.es)).toBeVisible();
      await Promise.all([page.waitForEvent("load"), page.getByRole("button", { name: copy.pwa.updateAction.es }).click()]);
      await expect.poll(() => version(page)).toBe(`${before}-next`);
    } finally {
      site.close();
    }
  });

  test("a plain reload already gets the new pages, notice or not", async ({ page }) => {
    const site = await deployCopy(3102);
    try {
      await page.goto(`${site.base}/`);
      await controlled(page);
      site.redeploy();
      await page.reload();
      await expect(page.locator('meta[name="build"]')).toHaveAttribute("content", "next");
    } finally {
      site.close();
    }
  });

  test("the emergency worker leaves no controller and no caches", async ({ page }) => {
    const site = await deployCopy(3103);
    try {
      await page.goto(`${site.base}/`);
      await controlled(page);
      expect((await page.evaluate(() => caches.keys())).length).toBeGreaterThan(0);

      site.kill();
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())!.update());
      // It reloads the tab itself; then nothing controls it and nothing is cached.
      await expect
        .poll(
          () =>
            page
              .evaluate(async () => ({
                controlled: navigator.serviceWorker.controller !== null,
                registrations: (await navigator.serviceWorker.getRegistrations()).length,
                caches: (await caches.keys()).length,
              }))
              // The worker reloads the tab mid-poll; that attempt simply does not count.
              .catch(() => null),
          { timeout: 15_000 },
        )
        .toEqual({ controlled: false, registrations: 0, caches: 0 });
    } finally {
      site.close();
    }
  });
});
