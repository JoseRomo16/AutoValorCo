/**
 * One stacked bar per vertical: how the model's importance splits between identity and
 * condition.
 *
 * Stacked rather than two separate bars because the parts sum to a whole and the question
 * is the proportion. Each segment carries its own percentage as text, so the figure is
 * readable without reading the pixels.
 */

export type Share = {
  label: string;
  segments: { label: string; value: number; tone: "identity" | "condition" | "other" }[];
  note: string;
};

const TONES: Record<Share["segments"][number]["tone"], string> = {
  identity: "bg-emerald-600",
  condition: "bg-sky-500",
  other: "bg-slate-300 dark:bg-slate-600",
};

export function ShareBar({ shares }: { shares: Share[] }) {
  return (
    <div className="space-y-5">
      {shares.map((share) => {
        const total = share.segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
        return (
          <div key={share.label}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="font-medium">{share.label}</span>
              <span className="text-sm text-slate-600 tnum dark:text-slate-400">{share.note}</span>
            </div>
            <div
              aria-hidden="true"
              className="flex h-7 overflow-hidden rounded bg-slate-100 dark:bg-slate-800"
            >
              {share.segments.map((segment) => (
                <span
                  key={segment.label}
                  className={`${TONES[segment.tone]} flex items-center justify-center text-[11px] font-medium text-white`}
                  style={{ width: `${(segment.value / total) * 100}%` }}
                >
                  {segment.value >= 12 ? `${Math.round(segment.value)}%` : ""}
                </span>
              ))}
            </div>
            <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-600 dark:text-slate-400">
              {share.segments.map((segment) => (
                <li key={segment.label} className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className={`inline-block h-2.5 w-2.5 rounded-sm ${TONES[segment.tone]}`}
                  />
                  <span>
                    {segment.label} <span className="tnum">{Math.round(segment.value)}%</span>
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
