import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * No colour in the front end that is not a theme token.
 *
 * `slate-*`, `emerald-*` and `sky-*` are the old palette, drawn for a white page: on the
 * dark theme they gave white chart tracks and unreadable labels, on paper cold blues that
 * belong to no system. A `dark:` utility is the same mistake from the other side — a second
 * colour typed by hand instead of a token that repaints with `data-theme`.
 */

const ROOT = process.cwd();
const SCANNED = ["app", "components", "lib"];

/**
 * Files still on the old palette, each with the block that removes it. An entry here is a
 * debt with an owner, not a permission: the test also fails if a listed file comes clean,
 * so the list cannot outlive its reason.
 */
const PENDING: Record<string, string> = {
  "components/Methodology.tsx": "Block 8 (feat/methodology-redesign)",
};

/** Class-like usages only: `dark:bg-…`, `text-slate-600`. A comment saying "`dark:`" is not one. */
const LEGACY = /\b(?:slate|emerald|sky)-\d{2,3}\b|\bdark:[a-z[]/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return files(full);
    return /\.(tsx?|css)$/.test(name) ? [full] : [];
  });
}

const ALL = SCANNED.flatMap((dir) => files(path.join(ROOT, dir))).map((file) =>
  path.relative(ROOT, file).split(path.sep).join("/"),
);

describe("legacy colour classes", () => {
  it("scans the front end", () => {
    expect(ALL.length).toBeGreaterThan(20);
  });

  it.each(ALL.filter((file) => !(file in PENDING)))("%s uses tokens only", (file) => {
    const hits = readFileSync(path.join(ROOT, file), "utf8")
      .split("\n")
      .map((line, index) => ({ line, number: index + 1 }))
      .filter(({ line }) => LEGACY.test(line))
      .map(({ line, number }) => `${number}: ${line.trim()}`);
    expect(hits).toEqual([]);
  });

  it.each(Object.entries(PENDING))("%s is still pending (%s)", (file) => {
    // When this fails, the file is clean: drop it from PENDING.
    expect(LEGACY.test(readFileSync(path.join(ROOT, file), "utf8"))).toBe(true);
  });
});
