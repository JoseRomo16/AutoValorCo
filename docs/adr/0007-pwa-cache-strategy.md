# ADR 0007 - The installable app and its cache strategy

- Status: **accepted**
- Date: 2026-11-03
- Block: 10 (`feat/pwa`)

## Context

The site is a static export on Render's free static plan, and only Valorar calls the API.
Making it installable needs a manifest and a service worker. Without care, a service
worker is also the easiest way to strand visitors on an old version, or to answer a price
request from a cache. The constraints were: zero cost, no change to the architecture, and
the API never answered from a cache.

The Next.js 16.4.2 documentation that ships in `node_modules/next/dist/docs` (context7 was
unreachable on the day) shows a hand-written `public/sw.js` in its PWA guide and only
suggests [Serwist](https://github.com/serwist/serwist) for offline caching.

## Decision

**A hand-written worker, generated after the build, no dependency.** The three strategies
below and the cache versioning are about 150 lines. Serwist would add a dependency and a
Turbopack integration to solve what the export already solves: Next puts a hash in every
asset name, and the list of files is simply the contents of `out/`. A worker of this size
can be read whole in review, which matters more here than features we would not use.

`scripts/sw.mjs` runs as `postbuild` and writes `out/sw.js` from `scripts/sw.template.js`:

| Request | Strategy |
| --- | --- |
| Any method other than GET | Not intercepted. POST `/predict` and `/explain` go straight to the network. |
| Other origins | Not intercepted, except GET to the API origin. |
| API `/catalog` (GET) | Network first. A good answer is saved in `autovalor-catalog`; offline, the saved copy is returned with `x-autovalor-cached-at`, and the form says its lists may be out of date. |
| Other API GETs (`/model-info`, `/health`, …) | Not intercepted: always the network, never a cache. |
| `/_next/static/*` | Cache first. The names carry a content hash and never change. |
| Pages and navigation payloads | Network first, so a deploy shows on the next load; offline, the cached copy matched **ignoring the query string** (a shared Valorar link opens Valorar with its offline message), then `/offline/`. |

**Versioning.** The version is a hash of every precached file and of the worker's own code,
so any change to the build is a new worker with a new cache, and the old caches are
deleted on `activate`. `autovalor-catalog` is kept across versions on purpose: it only
ever holds the last catalogue that worked.

**Updates.** A new worker installs and waits; the page shows a small "Hay una versión
nueva — Actualizar" bar and, when it is pressed, the worker takes over and the page
reloads once. Nobody is stuck on an old version when they ignore it: pages are network
first, so a plain reload already brings the new HTML, which asks for the new hashed assets
the old worker does not have and therefore fetches. `/sw.js` is served with
`Cache-Control: no-cache` and registered with `updateViaCache: "none"`, and the page checks
for an update whenever the tab returns to the foreground. All of it is in
`e2e/pwa.spec.ts`.

**Known limit.** The very first visit asks `/catalog` before the worker controls the page,
so the offline copy of the catalogue exists from the second load on.

**Manifest and icons** are written before the build by `scripts/pwa-assets.mjs`, the
icons drawn from the "CO" plate with `next/og` and every colour read from
`app/globals.css`; nothing binary is committed.

## The emergency worker

If the worker ever misbehaves, publish a build where `/sw.js` is `scripts/sw-kill.js`:

1. Set `NEXT_PUBLIC_SW_KILL=1` on the `autovalor-web` static site (Render → the service →
   Environment) and redeploy. `postbuild` then writes the emergency worker as `out/sw.js`,
   and the same variable makes every page render `<meta name="autovalor-sw" content="off">`,
   so the pages stop registering any worker and remove what they find. Without that second
   half the reloaded page would register the emergency worker again, in a loop.
2. Each visitor's browser checks `/sw.js` on the next navigation (it is never cached). The
   emergency worker installs at once, deletes every cache, unregisters itself and reloads
   the open tabs, which now load straight from the network.
3. Once the problem is fixed, remove the variable and redeploy; the normal worker comes
   back on the next visit.

`e2e/pwa.spec.ts` publishes it over an installed worker and checks the page ends with no
controller, no registration and no caches.

## Consequences

- Market and Methodology work offline; Valorar loads its form offline from the saved
  catalogue and says a price needs a connection.
- Cost stays at zero and the architecture does not change: the worker is one more static
  file.
- Two `headers` entries in `render.yaml` (`/sw.js` uncached, the manifest's content type)
  only apply once the Blueprint is synced.
