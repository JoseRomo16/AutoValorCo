/**
 * Read the theme tokens from `app/globals.css`, the one place colours are defined.
 *
 * The manifest, the PWA icons and the `theme-color` meta all need the ground and the plate
 * yellow. Reading them here keeps every one of those in step with the stylesheet instead of
 * repeating hex codes that a palette change would leave behind.
 *
 * Plain JavaScript so the prebuild scripts can use it under Node; `tokens.d.mts` types it
 * for the TypeScript that imports it (the layout's viewport).
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CSS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "globals.css");

/** The custom properties declared directly inside the first block opened by `selector {`. */
function block(css, selector) {
  const start = css.indexOf(`\n${selector} {`);
  if (start === -1) throw new Error(`globals.css has no "${selector}" block`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("\n}", open);
  const body = css.slice(open + 1, close);
  const tokens = {};
  for (const match of body.matchAll(/^\s*--([\w-]+):\s*([^;]+);/gm)) tokens[match[1]] = match[2].trim();
  return tokens;
}

/**
 * The dark theme is bare `:root` (also the no-JavaScript answer); light overrides it, so
 * a token light does not redefine falls back to the dark value, as it does in the browser.
 *
 * @param {string} [cssPath]
 * @returns {{ dark: Record<string, string>; light: Record<string, string> }}
 */
export function readThemeTokens(cssPath = CSS) {
  const css = readFileSync(cssPath, "utf-8").replace(/\r\n/g, "\n");
  const dark = block(css, ":root");
  const light = { ...dark, ...block(css, ':root[data-theme="light"]') };
  for (const name of ["ground", "accent", "ink"]) {
    if (!dark[name] || !light[name]) throw new Error(`globals.css does not define --${name}`);
  }
  return { dark, light };
}
