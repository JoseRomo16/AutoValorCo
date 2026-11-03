/**
 * Generate the PWA icons and the web app manifest into `public/`, before every build.
 *
 * The icons are the "CO" plate, the brand's mark, drawn by `next/og` like `og.png`: no
 * dependency, no binary committed, and a palette change in `globals.css` reaches them on
 * the next build. Written:
 *
 * - `icons/icon-192.png`, `icons/icon-512.png`: `purpose: "any"`, the plate on the ground;
 * - `icons/icon-maskable-512.png`: the plate inside the central 80 %, the safe zone a
 *   launcher may crop to any shape, with the ground bleeding to every edge;
 * - `icons/apple-touch-icon.png`, 180 px: what iOS puts on the home screen.
 *
 * `manifest.webmanifest` is written here too rather than as `app/manifest.ts`: it needs
 * the same tokens and the same icon list, and Render serves the `.webmanifest` extension
 * with its own content type, which `render.yaml` pins anyway.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

import { createElement as h } from "react";

import { readThemeTokens } from "./tokens.mjs";

const { ImageResponse } = createRequire(import.meta.url)("next/og");

const PUBLIC = path.join(process.cwd(), "public");
const ICONS = path.join(PUBLIC, "icons");

const { dark, light } = readThemeTokens();

/** The plate, scaled to `size` and drawn at `share` of it (1 = edge to edge). */
function plate(size, share) {
  const width = Math.round(size * share);
  const height = Math.round(width * 0.62);
  const ring = Math.max(2, Math.round(width * 0.045));
  return h(
    "div",
    {
      style: {
        display: "flex",
        width: size,
        height: size,
        alignItems: "center",
        justifyContent: "center",
        background: dark.ground,
      },
    },
    h(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width,
          height,
          borderRadius: Math.round(width * 0.11),
          background: dark.accent,
          border: `${ring}px solid ${dark.ground}`,
          boxShadow: `0 0 0 ${ring}px ${dark.accent}`,
          color: dark.ground,
          fontSize: Math.round(height * 0.56),
          fontWeight: 700,
          letterSpacing: Math.round(width * -0.01),
        },
      },
      "CO",
    ),
  );
}

async function png(name, size, share) {
  const image = new ImageResponse(plate(size, share), { width: size, height: size });
  const bytes = Buffer.from(await image.arrayBuffer());
  await writeFile(path.join(ICONS, name), bytes);
  return bytes.length;
}

await mkdir(ICONS, { recursive: true });

// The plate fills ~70 % of an "any" icon, where the platform draws it as given, and 60 %
// of the maskable one, comfortably inside the 80 % circle a launcher may crop to.
const ICON_SET = [
  { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any", size: 192, share: 0.72 },
  { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any", size: 512, share: 0.72 },
  {
    src: "/icons/icon-maskable-512.png",
    sizes: "512x512",
    type: "image/png",
    purpose: "maskable",
    size: 512,
    share: 0.6,
  },
];

for (const icon of ICON_SET) await png(path.basename(icon.src), icon.size, icon.share);
await png("apple-touch-icon.png", 180, 0.72);

const manifest = {
  id: "/",
  name: "AutoValor CO",
  short_name: "AutoValor",
  description:
    "Precio estimado, rango probable y los factores que lo mueven, para carros y motos usados en Colombia.",
  lang: "es",
  dir: "ltr",
  start_url: "/",
  scope: "/",
  display: "standalone",
  // The dark ground is the default theme and the plate's own field; the page repaints the
  // browser chrome per theme through the theme-color meta once it is running.
  background_color: dark.ground,
  theme_color: dark.ground,
  categories: ["finance", "utilities"],
  icons: ICON_SET.map(({ src, sizes, type, purpose }) => ({ src, sizes, type, purpose })),
};

await writeFile(path.join(PUBLIC, "manifest.webmanifest"), `${JSON.stringify(manifest, null, 2)}\n`);
process.stdout.write(
  `manifest.webmanifest and ${ICON_SET.length + 1} icons written (light ground ${light.ground}, dark ${dark.ground})\n`,
);
