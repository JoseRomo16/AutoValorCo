"use client";

/**
 * Horizontal bars with a 95 % confidence interval drawn on each one.
 *
 * Hand-built in HTML and CSS rather than with a charting library: the interval is not
 * decoration (an estimate whose interval crosses zero means something different from one
 * that does not, and that has to survive into the drawing), and the numbers are printed as
 * text beside every bar. Percent widths keep it fluid down to a phone with no measuring.
 *
 * Every colour is a theme token. The bar is what stands out, never its track: there is no
 * track, only a hairline base and the zero line in `--line-strong`, which is what gives the
 * chart its meaning. The drawing is `aria-hidden`; assistive technology gets the figure's
 * caption, which states the conclusion from the data, and a visually hidden table with
 * every value.
 */

import { useState } from "react";

/**
 * A wide interval keeps its series' colour as a 2 px outline over the pale fill. It used
 * to be the solid bar at 55 % opacity, which fell to 1.89:1 against paper (WCAG 1.4.11).
 */
const WIDE = "bg-bar-muted border-2 border-bar";

export type BarTone = "data" | "good" | "bad" | "accent";

export type BarItem = {
  /** Row label, already translated. Also the key for cross-chart highlighting. */
  label: string;
  value: number;
  /** Interval bounds in the same unit as `value`; omitted draws no whisker. */
  low?: number;
  high?: number;
  /** The value as it should read, with its unit and, on a signed chart, its sign. */
  valueText: string;
  /** Interval as it should read, when one exists. */
  intervalText?: string;
  /** A short qualifier: "indistinguishable from zero", "reference", "wide interval". */
  note?: string;
  /** The line under the figure when there is no note; defaults to the interval. */
  detail?: string;
  /** Draw a rule under this row: the whole-group row stands apart from its quartiles. */
  separatorAfter?: boolean;
  /** The estimate is not distinguishable from zero: faint fill, visible outline. */
  muted?: boolean;
  /** The interval is wider than the estimate: the bar recedes. */
  wide?: boolean;
  /** The reference row: an outline, not a magnitude. */
  reference?: boolean;
  /** Colour role; magnitudes default to the data grey. */
  tone?: BarTone;
  /** Shown on hover or tap: the figure and its interval in one line. */
  tooltip?: string;
};

type Props = {
  items: BarItem[];
  /** Bars grow left of zero as well as right. */
  signed?: boolean;
  /** The conclusion, from the data, for assistive technology. */
  caption: string;
  /** Column headings of the hidden table. */
  columns: { label: string; value: string; interval: string };
  /** The label currently highlighted across charts, if any. */
  highlight?: string | null;
  onHighlight?: (label: string | null) => void;
};

const FILL: Record<BarTone, string> = {
  data: "bg-bar border border-bar-edge",
  good: "bg-good",
  bad: "bg-bad",
  accent: "bg-accent-text",
};

function domain(items: BarItem[], signed: boolean): [number, number] {
  const values = items.flatMap((item) => [item.value, item.low ?? item.value, item.high ?? item.value]);
  const min = signed ? Math.min(0, ...values) : 0;
  const max = Math.max(0, ...values);
  const pad = (max - min) * 0.06 || 1;
  return [min - (signed ? pad : 0), max + pad];
}

export function IntervalBars({ items, signed = false, caption, columns, highlight, onHighlight }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const [min, max] = domain(items, signed);
  const span = max - min || 1;
  const position = (value: number) => ((value - min) / span) * 100;
  const zero = position(0);

  return (
    <figure className="m-0">
      <figcaption className="sr-only">{caption}</figcaption>
      {/* From `sm` up the list is one grid and each row a subgrid of it, so the figure
          column is as wide as the widest figure in this chart, up to 14 rem: a long note
          ("pocos anuncios, estimado menos preciso") wraps instead of squeezing the bars
          at 640-800 px. It was a fixed 12 rem, which left the figures far from the bars. */}
      <ul
        aria-hidden="true"
        className="space-y-1 sm:grid sm:grid-cols-[10rem_minmax(0,1fr)_fit-content(14rem)] sm:gap-x-3 sm:gap-y-1 sm:space-y-0"
      >
        {items.map((item) => {
          const value = position(item.value);
          const start = Math.min(zero, value);
          const width = Math.max(Math.abs(value - zero), 0.4);
          const dimmed = highlight != null && highlight !== item.label;
          const lit = highlight != null && highlight === item.label;
          const fill = item.reference
            ? "border border-dashed border-line-strong"
            : item.muted
              ? "bg-bar-muted border border-bar-edge"
              : FILL[item.tone ?? "data"];

          return (
            // Two layouts, one markup. On a phone the label and the figure share the first
            // row and the bar gets the full width underneath; from `sm` up it is the usual
            // three columns, and `order` puts the bar back in the middle.
            <li
              key={item.label}
              data-label={item.label}
              onMouseEnter={() => {
                setOpen(item.label);
                onHighlight?.(item.label);
              }}
              onMouseLeave={() => {
                setOpen(null);
                onHighlight?.(null);
              }}
              onClick={() => {
                const next = open === item.label ? null : item.label;
                setOpen(next);
                onHighlight?.(next);
              }}
              className={`relative grid cursor-default grid-cols-[minmax(7rem,1fr)_auto] items-center gap-x-3 gap-y-1 rounded px-1 py-1 transition-opacity duration-150 sm:col-span-3 sm:grid-cols-subgrid sm:gap-y-0 ${
                dimmed ? "opacity-40" : ""
              } ${lit ? "bg-surface" : ""} ${item.separatorAfter ? "mb-3 after:absolute after:inset-x-0 after:-bottom-2 after:h-px after:bg-line" : ""}`}
            >
              {/* Wraps between words instead of truncating: a cut label is a wrong label.
                  The 7 rem floor on phones matters as much: with breaks allowed anywhere, a
                  long note in the figure column squeezed "Norte de Santander" into a
                  column one letter wide. */}
              <span className="min-w-0 text-label text-muted [overflow-wrap:break-word]">
                {item.label}
              </span>

              <span className="max-w-[12rem] text-right font-mono text-value tnum sm:order-3 sm:max-w-none sm:pl-3">
                <span className={item.muted || item.reference ? "text-muted" : "font-medium text-ink"}>
                  {item.valueText}
                </span>
                {(item.note ?? item.detail ?? item.intervalText) && (
                  <span className="block text-detail text-muted">
                    {item.note ?? item.detail ?? item.intervalText}
                  </span>
                )}
              </span>

              <div className="col-span-2 flex items-center sm:order-2 sm:col-span-1">
                <div className="relative h-7 flex-1">
                  <span className="absolute inset-x-0 bottom-0 h-px bg-line" />
                  <span
                    className="absolute -inset-y-0.5 w-px bg-line-strong"
                    style={{ left: `${zero}%` }}
                  />
                  <span
                    data-mark=""
                    className={`absolute inset-y-1.5 rounded-sm ${item.wide && !item.muted && !item.reference ? WIDE : fill} ${
                      lit ? "outline-2 outline-offset-1 outline-accent-text" : ""
                    }`}
                    style={{ left: `${start}%`, width: `${width}%` }}
                  />
                  {item.low !== undefined && item.high !== undefined && (
                    <span
                      className="absolute top-1/2 h-2.5 -translate-y-1/2 border-x-2 border-muted"
                      style={{
                        left: `${position(item.low)}%`,
                        width: `${Math.max(position(item.high) - position(item.low), 0.3)}%`,
                      }}
                    >
                      <span data-mark="" className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-muted" />
                    </span>
                  )}
                  {open === item.label && item.tooltip && (
                    // Anchored to the track's left edge and never wider than it: a nowrap
                    // tooltip centred on the bar ran past a 320 px screen when tapped.
                    <span
                      role="tooltip"
                      className="pointer-events-none absolute bottom-full left-0 z-10 mb-1 w-max max-w-full rounded border border-line-strong bg-surface px-2 py-1 font-mono text-caption text-ink"
                    >
                      {item.tooltip}
                    </span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {/* The wrapper is what hides: a table ignores the 1 px width of `sr-only` and
          grows to its content, which put a horizontal scroll on phones. */}
      <div className="sr-only">
        <table>
          <thead>
            <tr>
              <th scope="col">{columns.label}</th>
              <th scope="col">{columns.value}</th>
              <th scope="col">{columns.interval}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.label}>
                <th scope="row">{item.label}</th>
                <td>{item.note ? `${item.valueText} (${item.note})` : item.valueText}</td>
                <td>{item.intervalText ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
