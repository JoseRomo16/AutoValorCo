/**
 * One stacked bar per vertical: how the model's importance splits between identity and
 * condition.
 *
 * Stacked rather than two separate bars because the parts sum to a whole and the question
 * is the proportion. Each segment prints its own percentage at 13 px on a fill measured for
 * it (`--seg-*` with `--on-seg`, 4.5:1 or better in both themes; `tokens.test.ts`). The
 * audit had found white 11 px type at 2.71:1. A segment too narrow for its number gets the
 * number underneath instead of a clipped one inside.
 */

export type ShareTone = "identity" | "condition" | "other";

export type Share = {
  label: string;
  segments: { label: string; value: number; valueText: string; tone: ShareTone }[];
  note: string;
};

const FILL: Record<ShareTone, string> = {
  identity: "bg-seg-identity text-on-seg",
  condition: "bg-seg-condition text-on-seg",
  // The remainder is pale by design, so its edge carries the 3:1 instead.
  other: "bg-seg-other border border-bar-edge text-ink",
};

/** Under this share of the bar a 13 px "16 %" no longer fits inside its segment. */
const MIN_INSIDE_PCT = 12;

export function ShareBar({ shares }: { shares: Share[] }) {
  return (
    <div className="space-y-7">
      {shares.map((share) => {
        const total = share.segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
        let start = 0;
        const placed = share.segments.map((segment) => {
          const width = (segment.value / total) * 100;
          const entry = { ...segment, width, middle: start + width / 2 };
          start += width;
          return entry;
        });
        const outside = placed.filter((segment) => segment.width < MIN_INSIDE_PCT);

        return (
          <div key={share.label}>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <span className="font-medium text-ink">{share.label}</span>
              <span className="font-mono text-detail text-muted tnum">{share.note}</span>
            </div>
            <div aria-hidden="true" className="flex h-8 overflow-hidden rounded-sm">
              {placed.map((segment) => (
                <span
                  key={segment.label}
                  data-mark=""
                  className={`${FILL[segment.tone]} flex items-center justify-center font-mono text-caption font-medium tnum`}
                  style={{ width: `${segment.width}%` }}
                >
                  {segment.width >= MIN_INSIDE_PCT ? segment.valueText : ""}
                </span>
              ))}
            </div>
            {outside.length > 0 && (
              <div aria-hidden="true" className="relative h-5">
                {outside.map((segment) => (
                  <span
                    key={segment.label}
                    className="absolute top-0.5 -translate-x-1/2 whitespace-nowrap font-mono text-caption text-muted tnum"
                    style={{ left: `${Math.min(Math.max(segment.middle, 6), 94)}%` }}
                  >
                    {segment.valueText}
                  </span>
                ))}
              </div>
            )}
            <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-caption text-muted">
              {placed.map((segment) => (
                <li key={segment.label} className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className={`inline-block h-3 w-3 rounded-sm ${FILL[segment.tone]}`}
                  />
                  <span>
                    {segment.label} <span className="font-mono tnum">{segment.valueText}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
