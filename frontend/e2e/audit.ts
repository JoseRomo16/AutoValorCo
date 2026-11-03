/**
 * The legibility audit, as one function the browser runs over the rendered page.
 *
 * Kept as plain browser code (no imports, no closures over Node values) because
 * `page.evaluate` serialises it. Every colour goes through a 1×1 canvas, which is how
 * `lab()`, `oklch()`, `rgb()` and `color-mix()` all become sRGB bytes; a colour the canvas
 * does not take is reported as a violation, never counted as a pass.
 */

export type AuditOptions = {
  /** Phones: touch targets 44 × 44 and axis numbers allowed down to 12 px. */
  mobile: boolean;
};

export type Violation = { rule: string; where: string; detail: string };

export function audit({ mobile }: AuditOptions): Violation[] {
  const violations: Violation[] = [];
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const context = canvas.getContext("2d", { willReadFrequently: true })!;

  type RGBA = [number, number, number, number];

  /** sRGB bytes and alpha 0–1, or null when the canvas cannot parse the colour. */
  function parse(colour: string): RGBA | null {
    if (colour === "transparent") return [0, 0, 0, 0];
    // Two different sentinels: a colour the canvas rejects leaves each one untouched.
    context.fillStyle = "#010203";
    context.fillStyle = colour;
    const first = context.fillStyle;
    context.fillStyle = "#040506";
    context.fillStyle = colour;
    if (first === "#010203" && context.fillStyle === "#040506") return null;
    context.clearRect(0, 0, 1, 1);
    context.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
    return [r!, g!, b!, a! / 255];
  }

  function over(top: RGBA, bottom: RGBA): RGBA {
    const a = top[3] + bottom[3] * (1 - top[3]);
    if (a === 0) return [0, 0, 0, 0];
    const mix = (i: number) => (top[i]! * top[3] + bottom[i]! * bottom[3] * (1 - top[3])) / a;
    return [mix(0), mix(1), mix(2), a];
  }

  function luminance([r, g, b]: RGBA): number {
    const channel = (v: number) => {
      const c = v / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  }

  function ratio(a: RGBA, b: RGBA): number {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi! + 0.05) / (lo! + 0.05);
  }

  function describe(element: Element): string {
    const id = element.id ? `#${element.id}` : "";
    const text = (element.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
    return `${element.tagName.toLowerCase()}${id} "${text}"`;
  }

  /**
   * The opaque colour behind an element, compositing every translucent background up the
   * tree onto the page. A gradient or image in the way cannot be reduced to one colour,
   * so it is an error rather than a guess.
   */
  function backdrop(element: Element): RGBA | string {
    const layers: RGBA[] = [];
    for (let node: Element | null = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.backgroundImage !== "none" && !node.closest("svg")) {
        return `background-image on ${describe(node)}`;
      }
      const colour = parse(style.backgroundColor);
      if (!colour) return `unparseable background ${style.backgroundColor}`;
      if (colour[3] > 0) layers.push(colour);
      if (colour[3] >= 1) break;
    }
    let result: RGBA = [255, 255, 255, 1];
    for (const layer of layers.reverse()) result = over(layer, result);
    return result;
  }

  /** The product of every ancestor's opacity: a faded parent fades its text too. */
  function opacity(element: Element): number {
    let value = 1;
    for (let node: Element | null = element; node; node = node.parentElement) {
      value *= Number(getComputedStyle(node).opacity);
    }
    return value;
  }

  function visible(element: Element): boolean {
    const rect = element.getBoundingClientRect();
    // A horizontal or vertical SVG line has no area, and is still a mark someone reads.
    const line = element instanceof SVGElement && element.tagName !== "svg" && element.tagName !== "text";
    if (line ? rect.width <= 1 && rect.height <= 1 : rect.width <= 1 || rect.height <= 1) {
      return false; // sr-only and the like
    }
    const style = getComputedStyle(element);
    if (style.visibility !== "visible" || style.display === "none") return false;
    return opacity(element) > 0.01;
  }

  function check(rule: string, element: Element, fg: string, minimum: number, faded = 1) {
    const colour = parse(fg);
    const behind = backdrop(element);
    if (!colour) {
      violations.push({ rule, where: describe(element), detail: `unparseable colour ${fg}` });
      return;
    }
    if (typeof behind === "string") {
      violations.push({ rule, where: describe(element), detail: behind });
      return;
    }
    const seen = over([colour[0], colour[1], colour[2], colour[3] * faded], behind);
    const value = ratio(seen, behind);
    if (value < minimum) {
      violations.push({
        rule,
        where: describe(element),
        detail: `${value.toFixed(2)}:1 < ${minimum}:1 (${fg} on rgb(${behind.slice(0, 3).map(Math.round).join(",")}))`,
      });
    }
  }

  // ---- text: size and contrast --------------------------------------------------------
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set<Element>();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!element || seen.has(element) || !(node.textContent ?? "").trim()) continue;
    seen.add(element);
    if (["SCRIPT", "STYLE", "NOSCRIPT", "OPTION", "TITLE"].includes(element.tagName)) continue;
    if (!visible(element)) continue;
    // Inactive controls are exempt from contrast (WCAG 1.4.3), not from size.
    const inactive = !!element.closest(":disabled, [aria-disabled='true']");
    const style = getComputedStyle(element);
    const inSvg = element instanceof SVGElement;

    let size = parseFloat(style.fontSize);
    if (inSvg) {
      const matrix = (element as unknown as SVGGraphicsElement).getScreenCTM?.();
      if (matrix) size *= Math.hypot(matrix.a, matrix.b);
    }
    const axis = inSvg && element.closest("[data-axis]") !== null;
    const floor = axis && mobile ? 12 : 13;
    if (size < floor - 0.05) {
      violations.push({
        rule: "text-size",
        where: describe(element),
        detail: `${size.toFixed(1)}px < ${floor}px`,
      });
    }
    if (!inactive) {
      check("text-contrast", element, inSvg ? style.fill : style.color, 4.5, opacity(element));
    }
  }

  // Placeholders are text too, and the form's ranges live in them.
  for (const input of document.querySelectorAll<HTMLInputElement>("input[placeholder]")) {
    if (!visible(input) || input.value !== "" || input.disabled) continue;
    const colour = getComputedStyle(input, "::placeholder").color;
    check("placeholder-contrast", input, colour, 4.5);
  }

  // ---- graphics: data marks, control borders ------------------------------------------
  for (const mark of document.querySelectorAll<SVGElement>(
    "svg line, svg polyline, svg path, svg circle",
  )) {
    if (mark.closest("[data-decorative]") || !visible(mark)) continue;
    const style = getComputedStyle(mark);
    if (style.stroke !== "none" && parseFloat(style.strokeWidth) > 0) {
      check("graphic-contrast", mark.ownerSVGElement ?? mark, style.stroke, 3, opacity(mark));
    } else if (style.fill !== "none") {
      check("graphic-contrast", mark.ownerSVGElement ?? mark, style.fill, 3, opacity(mark));
    }
  }
  for (const mark of document.querySelectorAll<HTMLElement>("[data-mark]")) {
    if (!visible(mark)) continue;
    const parent = mark.parentElement ?? mark;
    const style = getComputedStyle(mark);
    // A pale fill with a strong outline is read by its outline, so that is what is measured.
    const edge = parseFloat(style.borderTopWidth) > 0 ? style.borderTopColor : style.backgroundColor;
    check("graphic-contrast", parent, edge, 3, opacity(mark));
  }
  for (const control of document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
    "input:not([type=hidden]), select, textarea",
  )) {
    if (!visible(control) || control.disabled) continue;
    const style = getComputedStyle(control);
    if (parseFloat(style.borderBottomWidth) > 0) {
      check("control-border", control.parentElement ?? control, style.borderBottomColor, 3);
    }
  }

  // ---- layout: horizontal scroll ------------------------------------------------------
  const overflow = document.documentElement.scrollWidth - window.innerWidth;
  if (overflow > 0) {
    const culprit = [...document.querySelectorAll("body *")].find(
      (element) => element.getBoundingClientRect().right > window.innerWidth + 0.5 && visible(element),
    );
    violations.push({
      rule: "horizontal-scroll",
      where: culprit ? describe(culprit) : "document",
      detail: `${overflow}px wider than the viewport`,
    });
  }

  // ---- targets ------------------------------------------------------------------------
  const targets = document.querySelectorAll<HTMLElement>(
    "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [tabindex='0']",
  );
  for (const target of targets) {
    if (!visible(target) || target.closest("[aria-hidden='true']")) continue;
    const rect = target.getBoundingClientRect();
    // A target inside running text is exempt (WCAG 2.5.8 "inline"): enlarging it would
    // break the line it sits in. An inline link is recognised by its display; a term
    // button inside a paragraph declares itself with `data-inline`.
    const inline =
      target.hasAttribute("data-inline") ||
      (target.tagName === "A" && getComputedStyle(target).display === "inline");
    if (inline) continue;
    const minimum = mobile ? 44 : target.tagName === "A" ? 24 : 0;
    if (minimum === 0) continue;
    if (rect.width < minimum - 0.5 || rect.height < minimum - 0.5) {
      violations.push({
        rule: mobile ? "touch-target" : "link-target",
        where: describe(target),
        detail: `${rect.width.toFixed(0)}×${rect.height.toFixed(0)} < ${minimum}×${minimum}`,
      });
    }
  }

  return violations;
}
