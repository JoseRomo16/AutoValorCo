"use client";

/**
 * Value retained against age, one line per make.
 *
 * A line chart because the shape *is* the finding: the car curves bend down and the
 * motorcycle curves stay nearly flat. The SVG is drawn at the width of its column, measured,
 * rather than scaled from a fixed viewBox: scaling shrank the axis text on a phone and the
 * old fixed minimum width put a horizontal scrollbar on desktop. Text stays 13 px mono.
 *
 * Colour never carries identity alone. The make that holds most is a solid green line, the
 * one that holds least a dashed terracotta, the reference a dotted grey, and every line ends
 * in a direct label, so the chart reads under red-green colour blindness and in greyscale.
 */

import { useEffect, useRef, useState, type PointerEvent } from "react";

import { spreadLabels, type CurvePoint } from "@/lib/market";

export type CurveRole = "best" | "worst" | "reference";

export type Curve = {
  label: string;
  role: CurveRole;
  points: CurvePoint[];
};

type Props = {
  curves: Curve[];
  axisLabelX: string;
  axisLabelY: string;
  /** "59 % a los 10 años", already translated and formatted. */
  formatLastPoint: (point: CurvePoint) => string;
  /** One curve's value at one age, for the tooltip: "59 %". */
  formatValue: (retained: number) => string;
  /** The tooltip heading for an age: "A los 4 años". */
  formatAge: (age: number) => string;
  /** The conclusion, from the data, for assistive technology. */
  caption: string;
  /** Heading of the hidden table's first column. */
  brandColumn: string;
  highlight?: string | null;
  onHighlight?: (label: string | null) => void;
};

const STYLE: Record<CurveRole, { stroke: string; dash: string; width: number }> = {
  best: { stroke: "var(--good)", dash: "", width: 2.5 },
  worst: { stroke: "var(--bad)", dash: "8 5", width: 2.5 },
  reference: { stroke: "var(--bar)", dash: "1.5 4.5", width: 2.75 },
};

const HEIGHT = 300;
const FONT = 13;
const LABEL_GAP = FONT + 4;

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

function Swatch({ role }: { role: CurveRole }) {
  const style = STYLE[role];
  return (
    <svg aria-hidden="true" width="26" height="10" className="shrink-0">
      <line
        x1="1"
        x2="25"
        y1="5"
        y2="5"
        stroke={style.stroke}
        strokeWidth={style.width}
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
  formatLastPoint,
  formatValue,
  formatAge,
  caption,
  brandColumn,
  highlight,
  onHighlight,
}: Props) {
  const [box, width] = useWidth<HTMLDivElement>(560);
  const [hoverAge, setHoverAge] = useState<number | null>(null);

  const longest = Math.max(...curves.map((curve) => curve.label.length), 4);
  const pad = {
    top: 14,
    right: Math.min(longest * 8 + 30, width * 0.34),
    bottom: 46,
    left: 46,
  };
  const ages = curves.flatMap((curve) => curve.points.map((point) => point.age));
  const maxAge = Math.max(...ages, 1);
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = HEIGHT - pad.top - pad.bottom;
  const x = (age: number) => pad.left + (age / maxAge) * plotWidth;
  const y = (retained: number) => pad.top + (1 - retained / 100) * plotHeight;

  const lastOf = (curve: Curve) => curve.points[curve.points.length - 1];
  const labelY = spreadLabels(
    curves.map((curve) => y(lastOf(curve)?.retained ?? 0)),
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
          {[0, 25, 50, 75, 100].map((value) => (
            <g key={value}>
              <line
                x1={pad.left}
                x2={pad.left + plotWidth}
                y1={y(value)}
                y2={y(value)}
                stroke={value === 0 ? "var(--line-strong)" : "var(--grid)"}
                strokeWidth={1}
              />
              <text x={pad.left - 8} y={y(value) + 4} textAnchor="end" fill="var(--muted)">
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
              >
                {age}
              </text>
            ))}

          <text
            x={pad.left + plotWidth / 2}
            y={HEIGHT - 4}
            textAnchor="middle"
            fill="var(--muted)"
          >
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

          {curves.map((curve, index) => {
            const style = STYLE[curve.role];
            const dimmed = highlight != null && highlight !== curve.label;
            const lit = highlight != null && highlight === curve.label;
            const last = lastOf(curve);
            return (
              <g key={curve.label} opacity={dimmed ? 0.3 : 1} data-curve={curve.label}>
                <polyline
                  fill="none"
                  stroke={style.stroke}
                  strokeWidth={lit ? style.width + 1.25 : style.width}
                  strokeDasharray={style.dash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  points={curve.points.map((point) => `${x(point.age)},${y(point.retained)}`).join(" ")}
                />
                {last && (
                  <>
                    <line
                      x1={x(last.age) + 4}
                      x2={x(last.age) + 14}
                      y1={labelY[index]}
                      y2={labelY[index]}
                      stroke={style.stroke}
                      strokeWidth={style.width}
                      strokeDasharray={style.dash ? "3 2" : ""}
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

        {hoverAge !== null && (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-2 z-10 rounded border border-line-strong bg-surface px-2.5 py-1.5 font-mono text-xs text-ink"
            style={
              x(hoverAge) > width / 2
                ? { right: width - x(hoverAge) + 8 }
                : { left: x(hoverAge) + 8 }
            }
          >
            <p className="mb-0.5 text-muted">{formatAge(hoverAge)}</p>
            {curves.map((curve) => {
              const point = curve.points.find((candidate) => candidate.age === hoverAge);
              return point ? (
                <p key={curve.label} className="flex items-center gap-1.5 tnum">
                  <Swatch role={curve.role} />
                  {curve.label} {formatValue(point.retained)}
                </p>
              ) : null;
            })}
          </div>
        )}
      </div>

      <ul aria-hidden="true" className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 font-mono text-[13px]">
        {curves.map((curve) => {
          const last = lastOf(curve);
          return (
            <li
              key={curve.label}
              className="inline-flex items-center gap-2"
              onMouseEnter={() => onHighlight?.(curve.label)}
              onMouseLeave={() => onHighlight?.(null)}
            >
              <Swatch role={curve.role} />
              <span className="text-ink">{curve.label}</span>
              {last && <span className="text-muted tnum">{formatLastPoint(last)}</span>}
            </li>
          );
        })}
      </ul>

      <table className="sr-only">
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
          {curves.map((curve) => (
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
    </figure>
  );
}
