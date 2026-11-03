/*
 * Emergency service worker: removes the AutoValor CO worker and everything it cached.
 *
 * Publish it at /sw.js (build with `NEXT_PUBLIC_SW_KILL=1`, see docs/adr/0007-pwa-cache-strategy.md, which
 * also stops the pages registering a worker)
 * when the normal worker misbehaves. Browsers check /sw.js on every navigation and at least
 * once a day, and Render serves it with `Cache-Control: no-cache`, so each visitor picks
 * this up on their next visit. It takes over at once, deletes every cache, unregisters
 * itself and reloads the open tabs, which then load straight from the network with no
 * worker at all.
 */

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) await caches.delete(name);
      // Claim first: a worker can only navigate the tabs it controls.
      await self.clients.claim();
      await self.registration.unregister();
      for (const client of await self.clients.matchAll({ type: "window" })) {
        client.navigate(client.url);
      }
    })(),
  );
});
