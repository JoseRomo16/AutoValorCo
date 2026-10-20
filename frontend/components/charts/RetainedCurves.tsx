/**
 * Value retained against age, one line per make.
 *
 * A line chart because the shape *is* the finding: the car curves bend down and the
 * motorcycle curves are nearly flat, and no table makes that as immediate. SVG with a
 * fixed viewBox, wrapped in a horizontal scroller with a minimum width — scaling the whole
 * drawing down to a 360 px phone would shrink the labels to six pixels, so on a narrow
 * screen it scrolls instead of becoming unreadable.
 *
 * Every point is also printed in the legend at the oldest age shown, so the numbers are
 * available as text and not only as pixels.
 */

export type Curve = {
  label: string;
  points: { age: number; retained: number }[];
};

type Props = {
  curves: Curve[];
  axisLabelX: string;
  axisLabelY: string;
};

const WIDTH = 640;
const HEIGHT = 300;
const PAD = { top: 12, right: 12, bottom: 34, left: 40 };

/** Deliberately not a rainbow: six hues that stay distinguishable in both themes. */
const COLORS = ["#059669", "#0284c7", "#d97706", "#7c3aed", "#db2777", "#475569"];

export function RetainedCurves({ curves, axisLabelX, axisLabelY }: Props) {
  const ages = curves.flatMap((curve) => curve.points.map((point) => point.age));
  const maxAge = Math.max(...ages, 1);
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;

  const x = (age: number) => PAD.left + (age / maxAge) * plotWidth;
  const y = (retained: number) => PAD.top + (1 - retained / 100) * plotHeight;

  const gridlines = [0, 25, 50, 75, 100];

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full min-w-[34rem]"
        role="img"
        aria-label={`${axisLabelY} / ${axisLabelX}`}
      >
        {gridlines.map((value) => (
          <g key={value}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(value)}
              y2={y(value)}
              className="stroke-slate-200 dark:stroke-slate-700"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 6}
              y={y(value) + 4}
              textAnchor="end"
              className="fill-slate-500 text-[11px] dark:fill-slate-400"
            >
              {value}%
            </text>
          </g>
        ))}

        {Array.from({ length: maxAge + 1 }, (_, age) => age)
          .filter((age) => age % 2 === 0)
          .map((age) => (
            <text
              key={age}
              x={x(age)}
              y={HEIGHT - PAD.bottom + 16}
              textAnchor="middle"
              className="fill-slate-500 text-[11px] dark:fill-slate-400"
            >
              {age}
            </text>
          ))}

        <text
          x={PAD.left + plotWidth / 2}
          y={HEIGHT - 4}
          textAnchor="middle"
          className="fill-slate-500 text-[11px] dark:fill-slate-400"
        >
          {axisLabelX}
        </text>

        {curves.map((curve, index) => (
          <polyline
            key={curve.label}
            fill="none"
            stroke={COLORS[index % COLORS.length]}
            strokeWidth={2.25}
            strokeLinecap="round"
            points={curve.points.map((point) => `${x(point.age)},${y(point.retained)}`).join(" ")}
          />
        ))}
      </svg>

      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
        {curves.map((curve, index) => {
          const last = curve.points[curve.points.length - 1];
          return (
            <span key={curve.label} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: COLORS[index % COLORS.length] }}
              />
              <span className="font-medium text-slate-700 dark:text-slate-200">{curve.label}</span>
              {last && (
                <span className="tnum">
                  {Math.round(last.retained)}% · {last.age}
                </span>
              )}
            </span>
          );
        })}
      </figcaption>
    </figure>
  );
}
