"use client";

/**
 * The makes a reader compares on the retained-value chart, as toggle chips.
 *
 * One chip per make, each carrying what that make keeps at the oldest age so the list is
 * useful before anything is drawn. A pressed chip shows the colour and dash of its line,
 * which makes the chips the chart's legend as well. At the cap the free chips disable and
 * a live status says why, so a tap that does nothing is never silent.
 */

import { Swatch } from "./RetainedCurves";

export type BrandChip = {
  label: string;
  /** What the make keeps at the oldest age: "59 %". */
  valueText: string;
  /** A qualifier, e.g. the estimate is indistinguishable from zero. */
  note?: string;
};

type Props = {
  brands: BrandChip[];
  selected: string[];
  max: number;
  onToggle: (brand: string) => void;
  onReset: () => void;
  onClear: () => void;
  onHighlight?: (brand: string | null) => void;
  text: {
    /** The group's accessible name. */
    group: string;
    help: string;
    status: string;
    full: string;
    reset: string;
    clear: string;
  };
};

export function BrandPicker({
  brands,
  selected,
  max,
  onToggle,
  onReset,
  onClear,
  onHighlight,
  text,
}: Props) {
  const full = selected.length >= max;

  return (
    <div className="space-y-3">
      <p className="max-w-3xl text-detail text-muted">{text.help}</p>
      <div role="group" aria-label={text.group} className="flex flex-wrap gap-2">
        {brands.map((brand) => {
          const slot = selected.indexOf(brand.label);
          const pressed = slot !== -1;
          const disabled = !pressed && full;
          return (
            <button
              key={brand.label}
              type="button"
              aria-pressed={pressed}
              disabled={disabled}
              onClick={() => onToggle(brand.label)}
              onMouseEnter={() => onHighlight?.(brand.label)}
              onMouseLeave={() => onHighlight?.(null)}
              onFocus={() => onHighlight?.(brand.label)}
              onBlur={() => onHighlight?.(null)}
              className={`inline-flex min-h-10 items-center gap-2 rounded-full border px-3 py-1 text-left text-label transition-colors duration-150 ${
                pressed
                  ? "border-line-strong bg-surface text-ink"
                  : "border-line text-muted hover:border-line-strong hover:text-ink"
              } ${disabled ? "cursor-not-allowed opacity-50 hover:border-line hover:text-muted" : ""}`}
            >
              {pressed ? (
                <Swatch slot={slot} />
              ) : (
                <span aria-hidden="true" className="inline-block h-0.5 w-[26px] rounded bg-line-strong opacity-60" />
              )}
              <span>{brand.label}</span>
              <span className="font-mono text-caption text-muted tnum">{brand.valueText}</span>
              {brand.note && <span className="text-caption text-muted">({brand.note})</span>}
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p aria-live="polite" className="font-mono text-caption text-muted">
          {full ? text.full : text.status}
        </p>
        <button
          type="button"
          onClick={onReset}
          className="min-h-10 text-detail text-accent-text underline-offset-4 hover:underline"
        >
          {text.reset}
        </button>
        <button
          type="button"
          onClick={onClear}
          disabled={selected.length === 0}
          className="min-h-10 text-detail text-accent-text underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:text-muted disabled:no-underline"
        >
          {text.clear}
        </button>
      </div>
    </div>
  );
}
