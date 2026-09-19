import type { Metadata } from "next";
import Link from "next/link";

import { IdChip } from "@/components/id-chip";
import { StatusPill } from "@/components/status-pill";
import { loadData } from "@/lib/api/server";
import { BATCH_STATE_TONE, DISCREPANCY_STATE_TONE, OUTCOME_TONE, TONE_BAR_CLASS } from "@/lib/contract/status";
import { OUTCOMES } from "@/lib/contract/enums";
import { OUTCOME_LABEL } from "@/lib/contract/status";
import { formatCount, formatTimestamp, humanizeEnum, percent } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Overview — LEDGER" };

export default async function DashboardPage() {
  const [report, batches, exceptions, health] = await Promise.all([
    loadData("getReport"),
    loadData("listBatches"),
    loadData("listDiscrepancies"),
    loadData("getHealth"),
  ]);

  const totalCurrent = report.ok ? report.data.current_reconciliation_count : 0;
  const matched = report.ok ? (report.data.current_outcomes.MATCHED ?? 0) : 0;
  const matchRate = totalCurrent > 0 ? ((matched / totalCurrent) * 100).toFixed(1) : "—";
  const openExceptions = exceptions.ok
    ? exceptions.data.filter((d) => d.state === "OPEN").length
    : "—";
  const recentBatches = batches.ok ? batches.data.slice(-5).reverse() : [];
  const openQueue = exceptions.ok
    ? exceptions.data.filter((d) => d.state === "OPEN").slice(0, 5)
    : [];

  const serviceUp = health.ok;

  return (
    <div className="space-y-6">
      {/* Page title + service health */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Reconciliation Overview</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Live summary of ingestion, matching, and exception state.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-panel border border-line bg-surface px-3 py-2 text-2xs">
          <span
            className={`h-2 w-2 rounded-full ${serviceUp ? "bg-status-matched" : "bg-status-discrepancy"}`}
          />
          <span className="text-ink-muted">{serviceUp ? "Service operational" : "Service degraded"}</span>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-panel border border-line bg-surface px-4 py-4">
          <p className="text-2xs uppercase tracking-wide text-ink-muted">Decisions (current)</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-ink">
            {report.ok ? formatCount(totalCurrent) : "—"}
          </p>
        </div>
        <div className="rounded-panel border border-line bg-surface px-4 py-4">
          <p className="text-2xs uppercase tracking-wide text-ink-muted">Match rate</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-ink">
            {matchRate !== "—" ? `${matchRate}%` : "—"}
          </p>
        </div>
        <div className="rounded-panel border border-line bg-surface px-4 py-4">
          <p className="text-2xs uppercase tracking-wide text-ink-muted">Open exceptions</p>
          <p
            className={`mt-2 font-mono text-2xl font-semibold tabular-nums ${
              typeof openExceptions === "number" && openExceptions > 0
                ? "text-status-review"
                : "text-ink"
            }`}
          >
            {typeof openExceptions === "number" ? formatCount(openExceptions) : "—"}
          </p>
        </div>
        <div className="rounded-panel border border-line bg-surface px-4 py-4">
          <p className="text-2xs uppercase tracking-wide text-ink-muted">Total batches</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-ink">
            {batches.ok ? formatCount(batches.data.length) : "—"}
          </p>
        </div>
      </div>

      {/* Outcome distribution bar */}
      {report.ok && totalCurrent > 0 ? (
        <section className="rounded-panel border border-line bg-surface p-4">
          <h2 className="mb-3 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Outcome distribution — {formatCount(totalCurrent)} current decisions
          </h2>
          {/* Stacked bar */}
          <div className="flex h-6 w-full overflow-hidden rounded-full">
            {OUTCOMES.map((outcome) => {
              const count = report.data.current_outcomes[outcome] ?? 0;
              const share = (count / totalCurrent) * 100;
              if (share === 0) return null;
              return (
                <div
                  key={outcome}
                  className={TONE_BAR_CLASS[OUTCOME_TONE[outcome]]}
                  style={{ width: `${share.toFixed(2)}%` }}
                  title={`${OUTCOME_LABEL[outcome]}: ${formatCount(count)} (${share.toFixed(1)}%)`}
                />
              );
            })}
          </div>
          {/* Legend */}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
            {OUTCOMES.map((outcome) => {
              const count = report.data.current_outcomes[outcome] ?? 0;
              if (count === 0) return null;
              return (
                <div key={outcome} className="flex items-center gap-1.5 text-2xs">
                  <span
                    className={`h-2 w-2 rounded-sm ${TONE_BAR_CLASS[OUTCOME_TONE[outcome]]}`}
                  />
                  <span className="text-ink-muted">{OUTCOME_LABEL[outcome]}</span>
                  <span className="font-mono tabular-nums text-ink">
                    {formatCount(count)}
                  </span>
                  <span className="text-ink-subtle">
                    ({percent(count, totalCurrent)})
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Recent batches */}
        <section className="rounded-panel border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <h2 className="text-2xs font-medium uppercase tracking-wide text-ink-muted">
              Recent batches
            </h2>
            <Link href={route("/batches")} className="text-2xs text-accent">
              View all →
            </Link>
          </div>
          {recentBatches.length > 0 ? (
            <ul className="divide-y divide-line">
              {recentBatches.map((batch) => (
                <li key={batch.batch_id}>
                  <Link
                    href={route(`/batches?batch_id=${encodeURIComponent(batch.batch_id)}`)}
                    className="flex items-center justify-between px-4 py-3 no-underline hover:bg-surface-sunken"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-2xs text-ink">
                          <IdChip id={batch.batch_id} />
                        </span>
                        <StatusPill tone={BATCH_STATE_TONE[batch.state]}>
                          {humanizeEnum(batch.state)}
                        </StatusPill>
                      </div>
                      <p className="mt-0.5 text-2xs text-ink-muted">
                        {batch.source_id} · {formatTimestamp(batch.received_at)}
                      </p>
                    </div>
                    <span className="ml-4 shrink-0 font-mono tabular-nums text-sm text-ink">
                      {formatCount(batch.counters.received_count)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-6 text-center text-sm text-ink-muted">No batches yet.</p>
          )}
        </section>

        {/* Open exception queue */}
        <section className="rounded-panel border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <h2 className="text-2xs font-medium uppercase tracking-wide text-ink-muted">
              Open exceptions
            </h2>
            <Link href={route("/exceptions?state=OPEN")} className="text-2xs text-accent">
              View all →
            </Link>
          </div>
          {openQueue.length > 0 ? (
            <ul className="divide-y divide-line">
              {openQueue.map((exc) => (
                <li key={exc.discrepancy_id}>
                  <Link
                    href={route(`/exceptions/${encodeURIComponent(exc.discrepancy_id)}`)}
                    className="flex items-start gap-3 px-4 py-3 no-underline hover:bg-surface-sunken"
                  >
                    <StatusPill tone={DISCREPANCY_STATE_TONE[exc.state]}>
                      {humanizeEnum(exc.state)}
                    </StatusPill>
                    <div className="min-w-0">
                      <p className="font-mono text-2xs text-ink">
                        <IdChip id={exc.discrepancy_id} />
                      </p>
                      <p className="mt-0.5 truncate text-2xs text-ink-muted">{exc.reason}</p>
                    </div>
                    <span className="ml-auto shrink-0 text-2xs font-medium text-accent">
                      Resolve →
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-6 text-center text-sm text-ink-muted">
              No open exceptions.{" "}
              <Link href={route("/exceptions")} className="text-accent">
                View all exceptions
              </Link>
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
