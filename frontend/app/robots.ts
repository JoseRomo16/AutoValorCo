import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/links";

/*
 * Written to `out/robots.txt` at build time. `force-static` is what a static export needs
 * from a metadata route: without it Next treats the file as a route handler to run per
 * request, and there is no server to run it.
 *
 * The offline page is excluded here *and* by its own `noindex`: it is the worker's
 * fallback, not a page anyone should land on from a search.
 */
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: "/offline/" },
    sitemap: new URL("/sitemap.xml", SITE_URL).toString(),
  };
}
