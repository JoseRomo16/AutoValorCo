/*
 * AutoValor CO service worker. Generated: `scripts/sw.mjs` fills in the version, the
 * precache list and the API origin after `next build`, and writes `out/sw.js`.
 * The strategy and its reasons are in docs/adr/0007-pwa-cache-strategy.md.
 *
 * - Only GET is handled. POST (/predict, /explain) and every other method pass untouched.
 * - Other origins: only GET to the API origin is looked at; everything else is left alone.
 *   API answers are never served from cache, except /catalog as a fallback when the
 *   network fails, marked with `x-autovalor-cached-at` so the form can say it may be old.
 * - /_next/static/*: cache first. Those names carry a content hash, so they never change.
 * - Pages and their navigation payloads: network first, then the cache (ignoring the query
 *   string, so a shared Valorar link still opens Valorar offline), then /offline/.
 */

const VERSION = "__VERSION__";
const PRECACHE = __PRECACHE__;
const API_ORIGIN = "__API_ORIGIN__";

const CACHE = `autovalor-${VERSION}`;
// Kept across versions on purpose: it only ever holds the last /catalog that worked.
const CATALOG_CACHE = "autovalor-catalog";
const OFFLINE_PAGE = "/offline/";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)));
  // No skipWaiting here: a new version waits until the visitor accepts the update notice
  // (or every tab closes), so a page is never switched to new code underneath it.
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith("autovalor-") && name !== CACHE && name !== CATALOG_CACHE) {
          await caches.delete(name);
        }
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "GET_VERSION") event.ports[0]?.postMessage(VERSION);
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    if (url.origin === API_ORIGIN && url.pathname === "/catalog") {
      event.respondWith(catalog(request));
    }
    // Every other API call, and every other origin: not intercepted at all.
    return;
  }

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request));
    return;
  }
  event.respondWith(networkFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) (await caches.open(CACHE)).put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Keep the freshest copy of pages and payloads; a 404 is a real answer, not a page.
    if (response.ok) (await caches.open(CACHE)).put(stripSearch(request.url), response.clone());
    return response;
  } catch (error) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    if (request.mode === "navigate") {
      const offline = await caches.match(OFFLINE_PAGE);
      if (offline) return offline;
    }
    throw error;
  }
}

async function catalog(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const body = await response.clone().arrayBuffer();
      const headers = new Headers({
        "content-type": response.headers.get("content-type") ?? "application/json",
        "x-autovalor-cached-at": new Date().toISOString(),
        // The page reads this answer as a cross-origin one, so the header is only visible
        // to it if it is exposed, the way the API itself would have to expose it.
        "access-control-allow-origin": self.location.origin,
        "access-control-expose-headers": "x-autovalor-cached-at",
      });
      await (await caches.open(CATALOG_CACHE)).put("/catalog", new Response(body, { headers }));
    }
    return response;
  } catch (error) {
    const cached = await caches.match("/catalog", { cacheName: CATALOG_CACHE });
    if (cached) return cached;
    throw error;
  }
}

function stripSearch(href) {
  const url = new URL(href);
  url.search = "";
  return url.href;
}
