/**
 * The static export, served the way Render's static plan serves it, for the e2e suite.
 *
 * Twenty lines rather than a dependency: `/mercado/` resolves to `mercado/index.html`
 * (the export uses `trailingSlash`), and anything missing gets `404.html` with a 404
 * status, which is what the not-found test needs to see.
 */
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";

const ROOT = path.resolve(process.argv[2] ?? "out");
const PORT = Number(process.env.PORT ?? 3000);
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
};

function resolve(urlPath) {
  const clean = path.normalize(decodeURIComponent(urlPath)).replace(/^[/\\]+/, "");
  const file = path.join(ROOT, clean);
  if (!file.startsWith(ROOT)) return null;
  if (existsSync(file) && statSync(file).isFile()) return file;
  const index = path.join(file, "index.html");
  return existsSync(index) ? index : null;
}

createServer((request, response) => {
  const found = resolve(new URL(request.url ?? "/", "http://localhost").pathname);
  const file = found ?? path.join(ROOT, "404.html");
  response.writeHead(found ? 200 : 404, {
    "content-type": TYPES[path.extname(file)] ?? "application/octet-stream",
    // As render.yaml asks of Render: the worker script is always revalidated.
    ...(path.basename(file) === "sw.js" ? { "cache-control": "no-cache" } : {}),
  });
  createReadStream(file).pipe(response);
}).listen(PORT, () => console.log(`serving ${ROOT} on http://localhost:${PORT}`));
