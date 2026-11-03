"use client";

/**
 * Value retained against age: every make of the vertical, with the ones the reader picked
 * drawn in colour.
 *
 * A line chart because the shape *is* the finding: the car curves bend down and the
 * motorcycle curves stay nearly flat. The makes nobody picked stay on the chart as faint
 * grey lines, so a compared make is always read against the rest of the market rather than
 * on an empty canvas. The SVG is drawn at the measured width of its column, so text stays
 * 13 px mono and nothing scrolls sideways.
 *
 * Colour never carries identity alone: each selection slot has its own dash pattern, and
 * every coloured line ends in a direct label.
 */

import { useEffect, useRef, useState, type PointerEvent } from "react";

import { spreadLabels, type CurvePoint } from "@/lib/market";

export type Curve = {
  label: string;
  points: CurvePoint[];
  /** Position in the reader's selection, or null for a background line. */
  slot: number | null;
};

/** One look per selection slot: a series colour token and a dash pattern. */
export const SERIES = [
  { stroke: "var(--series-1)", dash: "" },
  { stroke: "var(--series-2)", dash: "8 5" },
  { stroke: "var(--series-3)", dash: "2 4" },
  { stroke: "var(--series-4)", dash: "10 4 2 4" },
  { stroke: "var(--series-5)", dash: "14 6" },
] as const;

const LINE_WIDTH = 2.5;

type Props = {
  curves: Curve[];
  axisLabelX: string;
  axisLabelY: string;
  /** One curve's value at one age: "59 %". */
  formatValue: (retained: number) => string;
  /** An age as a heading: "A los 4 años". */
  formatAge: (age: number) => string;
  /** The conclusion, from the data, for assistive technology. */
  caption: string;
  /** Heading of the hidden table's first column. */
  brandColumn: string;
  /** A make highlighted from another chart or from the make picker. */
  highlight?: string | null;
};

const HEIGHT = 300;
const FONT = 13;
const LABEL_GAP = FONT + 4;

/**
 * Where the vertical axis starts: ten points under the lowest value drawn, on a round
 * number.
 *
 * Every curve starts at 100 % by construction, so on a 0–100 axis the lines bunched in the
 * top third and the motorcycle curves, which barely fall, were one thick line. Lines are
 * read by their slope and their gaps, not by their length to a baseline, so the axis can
 * start where the data does; the chart's description says it does.
 */
export function axisFloor(curves: { points: CurvePoint[] }[]): number {
  const lowest = Math.min(...curves.flatMap((curve) => curve.points.map((point) => point.retained)));
  if (!Number.isFinite(lowest)) return 0;
  return Math.max(0, Math.floor((lowest - 10) / 10) * 10);
}

/** Gridlines from the floor to 100: every 10 points, or 25 on a tall range. */
export function axisTicks(floor: number): number[] {
  const step = 100 - floor > 70 ? 25 : 10;
  const ticks: number[] = [];
  for (let value = 100; value >= floor; value -= step) ticks.unshift(value);
  if (ticks[0] !== floor) ticks.unshift(floor);
  return ticks;
}

function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(Math.round(entry.contentRect.width), 240));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function Swatch({ slot }: { slot: number }) {
  const style = SERIES[slot % SERIES.length] ?? SERIES[0];
  return (
    <svg aria-hidden="true" width="26" height="10" className="shrink-0">
      <line
        x1="1"
        x2="25"
        y1="5"
        y2="5"
        stroke={style.stroke}
        strokeWidth={LINE_WIDTH}
        strokeDasharray={style.dash}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function RetainedCurves({
  curves,
  axisLabelX,
  axisLabelY,
  formatValue,
  formatAge,
  caption,
  brandColumn,
  highlight,
}: Props) {
  const [box, width] = useWidth<HTMLDivElement>(560);
  const [hoverAge, setHoverAge] = useState<number | null>(null);

  const chosen = curves
    .filter((curve): curve is Curve & { slot: number } => curve.slot !== null)
    .sort((a, b) => a.slot - b.slot);
  const background = curves.filter((curve) => curve.slot === null);

  const longest = Math.max(...chosen.map((curve) => curve.label.length), 4);
  const pad = {
    top: 14,
    right: Math.min(longest * 8 + 30, width * 0.34),
    bottom: 46,
    // Room for "100%" right-aligned against the plot and the rotated axis title beside it.
    left: 64,
  };
  const ages = curves.flatMap((curve) => curve.points.map((point) => point.age));
  const maxAge = Math.max(...ages, 1);
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = HEIGHT - pad.top - pad.bottom;
  const floor = axisFloor(curves);
  const gridlines = axisTicks(floor);
  const x = (age: number) => pad.left + (age / maxAge) * plotWidth;
  const y = (retained: number) => pad.top + (1 - (retained - floor) / (100 - floor)) * plotHeight;
  const line = (curve: Curve) =>
    curve.points.map((point) => `${x(point.age)},${y(point.retained)}`).join(" ");

  const lastOf = (curve: Curve) => curve.points[curve.points.length - 1];
  const labelY = spreadLabels(
    chosen.map((curve) => y(lastOf(curve)?.retained ?? 0)),
    LABEL_GAP,
    pad.top + FONT / 2,
    pad.top + plotHeight,
  );
  const tickStep = plotWidth < 260 ? 5 : 2;
  const allAges = [...new Set(ages)].sort((a, b) => a - b);

  // Hover with a mouse, tap with a finger: both land here and pick the nearest age.
  function pointerAt(event: PointerEvent<SVGRectElement>) {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scale = rect.width > 0 ? width / rect.width : 1;
    const local = (event.clientX - rect.left) * scale;
    const age = Math.round(((local - pad.left) / plotWidth) * maxAge);
    setHoverAge(Math.min(Math.max(age, 0), maxAge));
  }

  const atHover =
    hoverAge === null
      ? []
      : chosen
          .map((curve) => ({
            curve,
            point: curve.points.find((candidate) => candidate.age === hoverAge),
          }))
          .filter((entry) => entry.point !== undefined)
          .sort((a, b) => (b.point?.retained ?? 0) - (a.point?.retained ?? 0));

  return (
    <figure className="m-0">
      <figcaption className="sr-only">{caption}</figcaption>
      <div ref={box} className="relative w-full">
        <svg
          aria-hidden="true"
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          className="block h-auto max-w-full font-mono"
          style={{ fontSize: FONT }}
        >
          {gridlines.map((value) => (
            <g key={value}>
              <line
                x1={pad.left}
                x2={pad.left + plotWidth}
                y1={y(value)}
                y2={y(value)}
                stroke={value === floor ? "var(--line-strong)" : "var(--grid)"}
                strokeWidth={1}
                // Gridlines are reading aids, not marks: WCAG 1.4.11 asks 3:1 of what is
                // needed to understand the chart, and the values are on the axis and in the
                // table. The baseline is a mark and keeps line-strong.
                data-decorative={value === floor ? undefined : ""}
              />
              <text x={pad.left - 8} y={y(value) + 4} textAnchor="end" fill="var(--muted)" data-axis="">
                {value}%
              </text>
            </g>
          ))}

          {Array.from({ length: maxAge + 1 }, (_, age) => age)
            .filter((age) => age % tickStep === 0)
            .map((age) => (
              <text
                key={age}
                x={x(age)}
                y={pad.top + plotHeight + 20}
                textAnchor="middle"
                fill="var(--muted)"
                data-axis=""
              >
                {age}
              </text>
            ))}

          <text x={pad.left + plotWidth / 2} y={HEIGHT - 4} textAnchor="middle" fill="var(--muted)">
            {axisLabelX}
          </text>
          <text
            x={12}
            y={pad.top + plotHeight / 2}
            textAnchor="middle"
            fill="var(--muted)"
            transform={`rotate(-90 12 ${pad.top + plotHeight / 2})`}
          >
            {axisLabelY}
          </text>

          {background.map((curve) => (
            <polyline
              key={curve.label}
              data-curve={curve.label}
              data-background="true"
              fill="none"
              stroke="var(--line-strong)"
              strokeOpacity={highlight === curve.label ? 1 : 0.5}
              strokeWidth={highlight === curve.label ? 2 : 1.25}
              strokeLinejoin="round"
              points={line(curve)}
            />
          ))}

          {hoverAge !== null && (
            <line
              x1={x(hoverAge)}
              x2={x(hoverAge)}
              y1={pad.top}
              y2={pad.top + plotHeight}
              stroke="var(--line-strong)"
              strokeWidth={1}
            />
          )}

          {chosen.map((curve, index) => {
            const style = SERIES[curve.slot % SERIES.length] ?? SERIES[0];
            const dimmed = highlight != null && highlight !== curve.label;
            const lit = highlight != null && highlight === curve.label;
            const last = lastOf(curve);
            return (
              <g key={curve.label} opacity={dimmed ? 0.35 : 1} data-curve={curve.label}>
                <polyline
                  fill="none"
                  stroke={style.stroke}
                  strokeWidth={lit ? LINE_WIDTH + 1.25 : LINE_WIDTH}
                  strokeDasharray={style.dash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  points={line(curve)}
                />
                {last && (
                  <>
                    <line
                      x1={x(last.age) + 4}
                      x2={x(last.age) + 14}
                      y1={labelY[index]}
                      y2={labelY[index]}
                      stroke={style.stroke}
                      strokeWidth={LINE_WIDTH}
                    />
                    <text
                      x={x(last.age) + 18}
                      y={(labelY[index] ?? 0) + 4}
                      fill="var(--ink)"
                      fontWeight={lit ? 600 : 400}
                    >
                      {curve.label}
                    </text>
                  </>
                )}
              </g>
            );
          })}

          <rect
            x={pad.left}
            y={pad.top}
            width={plotWidth}
            height={plotHeight}
            fill="transparent"
            onPointerMove={(event) => pointerAt(event)}
            onPointerDown={(event) => pointerAt(event)}
            onPointerLeave={() => setHoverAge(null)}
          />
        </svg>

        {hoverAge !== null && atHover.length > 0 && (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-2 z-10 rounded border border-line-strong bg-surface px-2.5 py-1.5 font-mono text-caption text-ink"
            style={x(hoverAge) > width / 2 ? { right: width - x(hoverAge) + 8 } : { left: x(hoverAge) + 8 }}
          >
            <p className="mb-0.5 text-muted">{formatAge(hoverAge)}</p>
            {atHover.map(({ curve, point }) => (
              <p key={curve.label} className="flex items-center gap-1.5 tnum">
                <Swatch slot={curve.slot} />
                {curve.label} {formatValue(point?.retained ?? 0)}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Every make, compared or not: the drawing shows five at most, the data has all. The
          wrapper is what hides, because a table ignores the 1 px width of `sr-only`. */}
      <div className="sr-only">
        <table>
          <thead>
            <tr>
              <th scope="col">{brandColumn}</th>
              {allAges.map((age) => (
                <th key={age} scope="col">
                  {formatAge(age)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...chosen, ...background].map((curve) => (
              <tr key={curve.label}>
                <th scope="row">{curve.label}</th>
                {allAges.map((age) => {
                  const point = curve.points.find((candidate) => candidate.age === age);
                  return <td key={age}>{point ? formatValue(point.retained) : "—"}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
