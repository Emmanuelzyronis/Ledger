import type { ReactNode } from "react";

export interface Stat {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}

/** One border-separated band of single-value stats. Not a row of floating cards. */
export function SummaryBand({
  stats,
  columns = 4,
}: {
  stats: readonly Stat[];
  columns?: 3 | 4 | 5 | 6;
}) {
  const grid =
    columns === 3
      ? "sm:grid-cols-3"
      : columns === 5
        ? "sm:grid-cols-3 lg:grid-cols-5"
        : columns === 6
          ? "sm:grid-cols-3 lg:grid-cols-6"
          : "sm:grid-cols-2 lg:grid-cols-4";
  return (
    <dl
      className={`mb-4 grid grid-cols-1 divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface sm:divide-y-0 sm:divide-x ${grid}`}
    >
      {stats.map((stat) => (
        <div key={stat.label} className="px-4 py-3">
          <dt className="text-2xs uppercase tracking-wide text-ink-muted">{stat.label}</dt>
          <dd className="mt-1 font-mono text-xl tabular-nums text-ink">{stat.value}</dd>
          {stat.detail ? <dd className="mt-1 text-2xs text-ink-subtle">{stat.detail}</dd> : null}
        </div>
      ))}
    </dl>
  );
}
