import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/links";

export const dynamic = "force-static";

/** The three pages, with the trailing slash the export serves them at (`next.config.mjs`). */
export const SITEMAP_PATHS = ["/", "/mercado/", "/metodologia/"] as const;

/*
 * No `lastModified`: the build date would change the file on every build, and with it the
 * service worker's version hash (`scripts/sw.mjs`), turning an identical deploy into an
 * update notice for every visitor.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return SITEMAP_PATHS.map((path) => ({ url: new URL(path, SITE_URL).toString() }));
}
