/**
 * Write `out/sw.js` after `next build` (the `postbuild` script).
 *
 * The precache list is read from the export itself: every file under `out/` except the
 * service worker, the social card, the crawler files and source maps. That is the shell (the four pages, the
 * offline page and their navigation payloads), the hashed `/_next/static` assets, the
 * icons and the manifest. The version is a hash of those files' contents, so any change
 * to the build produces a new worker and a new cache, and an identical build does not.
 *
 * `NEXT_PUBLIC_SW_KILL=1` publishes the emergency worker (`scripts/sw-kill.js`) instead, and
 * the same variable makes the pages stop registering any worker; see ADR 0007.
 */

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(process.argv[2] ?? path.join(HERE, "..", "out"));
// Crawler files are never needed offline, so they stay out of the precache.
const SKIP = new Set(["sw.js", "og.png", "robots.txt", "sitemap.xml"]);

/** The API's origin, as the bundle was built with it (`lib/api.ts` reads the same variable). */
function apiOrigin() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured) return new URL(configured).origin;
  const source = readFileSync(path.join(HERE, "..", "lib", "api.ts"), "utf-8");
  const fallback = source.match(/NEXT_PUBLIC_API_BASE_URL\s*\?\?\s*"([^"]+)"/);
  if (!fallback) throw new Error("lib/api.ts no longer names a default API URL");
  return new URL(fallback[1]).origin;
}

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

/** `out/mercado/index.html` is served as `/mercado/`; everything else at its own path. */
function urlOf(file) {
  const relative = path.relative(OUT, file).split(path.sep).join("/");
  if (relative === "index.html") return "/";
  if (relative.endsWith("/index.html")) return `/${relative.slice(0, -"index.html".length)}`;
  return `/${relative}`;
}

if (process.env.NEXT_PUBLIC_SW_KILL === "1") {
  writeFileSync(path.join(OUT, "sw.js"), readFileSync(path.join(HERE, "sw-kill.js")));
  process.stdout.write("sw.js: the emergency worker (NEXT_PUBLIC_SW_KILL=1)\n");
} else {
  const files = walk(OUT)
    .filter((file) => !SKIP.has(path.basename(file)) && !file.endsWith(".map"))
    .sort();
  const template = readFileSync(path.join(HERE, "sw.template.js"), "utf-8");
  // The worker's own code is part of the version: a change to the strategy alone must
  // still reach visitors as a new worker with a new cache.
  const hash = createHash("sha256").update(template).update(apiOrigin());
  for (const file of files) hash.update(urlOf(file)).update(readFileSync(file));
  const version = hash.digest("hex").slice(0, 12);
  const precache = files.map(urlOf);
  const source = template
    .replace("__VERSION__", version)
    .replace("__PRECACHE__", JSON.stringify(precache))
    .replace("__API_ORIGIN__", apiOrigin());
  writeFileSync(path.join(OUT, "sw.js"), source);
  const bytes = files.reduce((sum, file) => sum + statSync(file).size, 0);
  process.stdout.write(
    `sw.js: version ${version}, ${precache.length} files precached (${(bytes / 1e6).toFixed(2)} MB)\n`,
  );
}
