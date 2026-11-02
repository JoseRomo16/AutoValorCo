/**
 * Generate `public/og.png`, the 1200x630 card LinkedIn, WhatsApp and Facebook show.
 *
 * It used to be `og.svg`, which none of those three render: the preview came out blank
 * everywhere the link was actually shared.
 *
 * **Why a script and not `app/opengraph-image.tsx`.** That route does work under
 * `output: "export"` — with `export const dynamic = "force-static"` added, which the build
 * refuses to proceed without — and it emits a correct PNG. But it emits it at
 * `out/opengraph-image`, with no file extension, and puts `/opengraph-image?<hash>` in the
 * meta tag. Render's static plan serves files by extension, and every one of these crawlers
 * fetches the URL and checks the `Content-Type` before showing anything. Verified on
 * 2026-11-02: the bytes are a valid PNG, the path is extensionless. A `.png` under
 * `public/` removes that question instead of leaving it to be discovered by sharing a link.
 *
 * `next/og` does the rendering, so this adds no dependency: it is the same engine the route
 * would have used, called directly. No JSX, because this file is run by plain Node before
 * the build — `createElement` is the whole difference.
 *
 * **No figure is written here.** The card carries the brand, the plate and the promise; it
 * does not quote a MAPE or a row count, which is the rule that keeps numbers out of
 * anything not generated from `model.json`.
 *
 * Run by `npm run build` through `prebuild`, so a clone that builds gets the image without
 * knowing this exists.
 */

import { writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

import { createElement as h } from "react";

// `next/og` is a CommonJS entry with no ESM export map, so `import` from it fails from a
// plain .mjs. `createRequire` goes through that public entry rather than reaching into
// `next/dist/server/og/...`, which is an internal path that may move between releases.
const { ImageResponse } = createRequire(import.meta.url)("next/og");

const OUT = path.join(process.cwd(), "public", "og.png");

/** The site's own tokens, so the card cannot drift from the page it advertises. */
const INK = "#f2efe6";
const GROUND = "#14130f";
const ACCENT = "#f6c800";
const MUTED = "#a39e8f";
const FAINT = "#8a8577";

const sans = "Arial Black, Arial, sans-serif";
const mono = "Consolas, monospace";

/** The "CO" plate, which is the mark's one piece of local colour. */
function plate() {
  return h(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 62,
        height: 46,
        marginLeft: 16,
        borderRadius: 7,
        background: ACCENT,
        border: `3px solid ${GROUND}`,
        boxShadow: `0 0 0 3px ${ACCENT}`,
        color: GROUND,
        fontFamily: mono,
        fontSize: 22,
      },
    },
    "CO",
  );
}

/**
 * The band, drawn rather than described.
 *
 * It is the thing this product has that a plain estimator does not, so the card shows its
 * shape: a range, the estimate inside it, and the asking price against it.
 */
function band() {
  return h(
    "div",
    { style: { display: "flex", flexDirection: "column", width: 1008, marginTop: 56 } },
    h(
      "div",
      {
        style: {
          display: "flex",
          position: "relative",
          height: 34,
          borderRadius: 4,
          background: "#2b2923",
        },
      },
      h("div", {
        style: {
          position: "absolute",
          left: 212,
          top: 9,
          width: 560,
          height: 16,
          borderRadius: 2,
          background: "#45423a",
        },
      }),
      h("div", {
        style: { position: "absolute", left: 474, top: 3, width: 3, height: 28, background: INK },
      }),
      h("div", {
        style: {
          position: "absolute",
          left: 556,
          top: -3,
          width: 5,
          height: 40,
          borderRadius: 2,
          background: ACCENT,
        },
      }),
    ),
    h(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          width: 560,
          marginLeft: 212,
          marginTop: 10,
          color: FAINT,
          fontFamily: mono,
          fontSize: 20,
        },
      },
      h("div", {}, "P10"),
      h("div", {}, "P90"),
    ),
  );
}

function card() {
  return h(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column",
        width: "100%",
        height: "100%",
        padding: "120px 96px 0",
        background: GROUND,
        borderTop: `6px solid ${ACCENT}`,
        color: INK,
      },
    },
    h(
      "div",
      { style: { display: "flex", alignItems: "center" } },
      h("div", { style: { fontFamily: sans, fontSize: 44, letterSpacing: -1 } }, "AutoValor"),
      plate(),
    ),
    h(
      "div",
      { style: { display: "flex", flexDirection: "column", marginTop: 40 } },
      h(
        "div",
        { style: { fontFamily: sans, fontSize: 82, letterSpacing: -2, lineHeight: 1.1 } },
        "Cuánto vale tu carro",
      ),
      h(
        "div",
        { style: { fontFamily: sans, fontSize: 82, letterSpacing: -2, lineHeight: 1.1 } },
        "o tu moto usada",
      ),
    ),
    h(
      "div",
      { style: { display: "flex", marginTop: 32, color: MUTED, fontSize: 30 } },
      "Precio estimado, rango probable y qué lo mueve.",
    ),
    band(),
  );
}

const response = new ImageResponse(card(), { width: 1200, height: 630 });
const bytes = Buffer.from(await response.arrayBuffer());

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, bytes);

if (bytes.subarray(0, 4).toString("hex") !== "89504e47") {
  throw new Error("og.png is not a PNG; the renderer returned something else");
}
process.stdout.write(`og.png written: ${bytes.length} bytes, 1200x630\n`);
