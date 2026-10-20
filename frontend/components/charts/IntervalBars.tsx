/**
 * Horizontal bars with a 95 % confidence interval drawn on each one.
 *
 * Hand-built in HTML and CSS rather than with a charting library, for two reasons that
 * both matter here. The interval is not decoration — an estimate whose interval crosses
 * zero means something different from one that does not, and that distinction has to
 * survive into the rendering. And the numbers are printed as text next to every bar, so
 * the chart is readable by a screen reader without an alternative table: the bars are
 * `aria-hidden` and the data is the markup.
 *
 * Percentages for widths, so the whole thing is fluid down to a phone with no media
 * queries and no measuring of the container.
 */

export type BarItem = {
  /** Row label, already translated. */
  label: string;
  value: number;
  /** Interval bounds in the same unit as `value`; omitted draws no whisker. */
  low?: number;
  high?: number;
  /** The value as it should read, with its unit. */
  valueText: string;
  /** Interval as it should read, when one exists. */
  intervalText?: string;
  /** A short qualifier: "indistinguishable from zero", "reference". */
  note?: string;
  /** Drawn pale: the estimate is not distinguishable from zero. */
  muted?: boolean;
};

type Props = {
  items: BarItem[];
  /** Bars grow left of zero as well as right. */
  signed?: boolean;
};

function domain(items: BarItem[], signed: boolean): [number, number] {
  const values = items.flatMap((item) => [item.value, item.low ?? item.value, item.high ?? item.value]);
  const min = signed ? Math.min(0, ...values) : 0;
  const max = Math.max(0, ...values);
  const pad = (max - min) * 0.06 || 1;
  return [min - (signed ? pad : 0), max + pad];
}

export function IntervalBars({ items, signed = false }: Props) {
  const [min, max] = domain(items, signed);
  const span = max - min || 1;
  const position = (value: number) => ((value - min) / span) * 100;
  const zero = position(0);

  return (
    <ul className="space-y-1.5">
      {items.map((item) => {
        const value = position(item.value);
        const start = Math.min(zero, value);
        const width = Math.max(Math.abs(value - zero), 0.4);
        const negative = item.value < 0;

        return (
          // Two layouts, one markup. On a phone the label and the figure share the first
          // row and the bar gets the full width underneath, because a 170 px track next
          // to a 120 px label is a bar nobody can read. From `sm` up it is the usual
          // three columns, and `order` puts the bar back in the middle.
          <li
            key={item.label}
            className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[9rem_minmax(0,1fr)_10rem] sm:gap-y-0"
          >
            <span className="truncate text-sm text-slate-700 dark:text-slate-300" title={item.label}>
              {item.label}
            </span>

            <span className="text-right text-sm tnum sm:order-3 sm:pl-3">
              <span className={item.muted ? "text-slate-500 dark:text-slate-400" : "font-medium"}>
                {item.valueText}
              </span>
              {item.note && (
                <span className="block text-xs text-slate-500 dark:text-slate-400">{item.note}</span>
              )}
              {!item.note && item.intervalText && (
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  {item.intervalText}
                </span>
              )}
            </span>
            <div className="col-span-2 flex items-center sm:order-2 sm:col-span-1">
              <div
                aria-hidden="true"
                className="relative h-6 flex-1 rounded bg-slate-100 dark:bg-slate-800"
              >
                {signed && (
                  <span
                    className="absolute inset-y-0 w-px bg-slate-300 dark:bg-slate-600"
                    style={{ left: `${zero}%` }}
                  />
                )}

                <span
                  className={`absolute inset-y-1 rounded-sm ${
                    item.muted
                      ? "bg-slate-300 dark:bg-slate-600"
                      : negative
                        ? "bg-sky-500/80"
                        : "bg-emerald-600/80"
                  }`}
                  style={{ left: `${start}%`, width: `${width}%` }}
                />

                {item.low !== undefined && item.high !== undefined && (
                  <span
                    className="absolute top-1/2 h-2 -translate-y-1/2 border-x-2 border-slate-500/70 dark:border-slate-300/70"
                    style={{
                      left: `${position(item.low)}%`,
                      width: `${Math.max(position(item.high) - position(item.low), 0.3)}%`,
                    }}
                  >
                    <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-slate-500/70 dark:bg-slate-300/70" />
                  </span>
                )}
              </div>
            </div>

          </li>
        );
      })}
    </ul>
  );
}
