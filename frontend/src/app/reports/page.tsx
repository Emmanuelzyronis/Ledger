import type { Metadata } from "next";

import { ContractCalls } from "@/components/contract-calls";
import { PageHeader } from "@/components/page-header";
import { OperationLabel } from "@/components/operation-label";
import { PlaceholderNotice } from "@/components/placeholder-notice";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { OUTCOMES } from "@/lib/contract/enums";
import { PLACEHOLDER_REPORT } from "@/lib/contract/placeholder";
import { OUTCOME_LABEL, OUTCOME_TONE, TONE_BAR_CLASS } from "@/lib/contract/status";
import { formatCount, formatTimestamp, percent } from "@/lib/format";

export const metadata: Metadata = { title: "Reports — LEDGER" };

const CONTRACT_OPERATIONS = ["getReport", "exportData"] as const;

export default function ReportsPage() {
  const report = PLACEHOLDER_REPORT;
  const stats: readonly Stat[] = [
    { label: "Batch", value: report.batch_id ?? "all", detail: "batch_id filter" },
    {
      label: "Reconciliation decisions",
      value: formatCount(report.reconciliation_count),
      detail: "all versions",
    },
    { label: "Current versions", value: formatCount(report.current_reconciliation_count) },
    { label: "Discrepancies", value: formatCount(report.discrepancy_count) },
    {
      label: "Source events",
      value: formatCount(report.source_watermark.event_count),
      detail: "watermark count",
    },
    {
      label: "Watermark time",
      value: report.source_watermark.timestamp
        ? formatTimestamp(report.source_watermark.timestamp)
        : "—",
    },
  ];

  return (
    <>
      <PageHeader
        title="Reports"
        description="Read-only projections derived from authoritative reconciliation state. Reports and exports are never a source of truth and never mutate a decision."
      />
      <PlaceholderNotice what="the report projection" />
      <SummaryBand stats={stats} columns={6} />

      <h2 className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Outcomes — all versions vs current
      </h2>
      <Table caption="Outcome counts">
        <THead>
          <Tr>
            <Th>Outcome</Th>
            <Th align="right">All versions</Th>
            <Th align="right">Current</Th>
            <Th>Current share</Th>
          </Tr>
        </THead>
        <TBody>
          {OUTCOMES.map((outcome) => {
            const current = report.current_outcomes[outcome] ?? 0;
            const share = (current / report.current_reconciliation_count) * 100;
            return (
              <Tr key={outcome} accent={OUTCOME_TONE[outcome]}>
                <Td className="whitespace-nowrap">
                  <StatusPill tone={OUTCOME_TONE[outcome]}>{OUTCOME_LABEL[outcome]}</StatusPill>
                  <span className="ml-2 font-mono text-2xs text-ink-subtle">{outcome}</span>
                </Td>
                <Td align="right" className="font-mono tabular-nums">
                  {formatCount(report.outcomes[outcome] ?? 0)}
                </Td>
                <Td align="right" className="font-mono tabular-nums">
                  {formatCount(current)}
                </Td>
                <Td className="w-[200px]">
                  <div className="flex items-center gap-3">
                    <span className="w-10 shrink-0 text-right font-mono text-2xs tabular-nums text-ink-muted">
                      {percent(current, report.current_reconciliation_count)}
                    </span>
                    <span className="block h-1 w-full bg-surface-sunken">
                      <span
                        className={`block h-1 ${TONE_BAR_CLASS[OUTCOME_TONE[outcome]]}`}
                        style={{ width: `${share.toFixed(1)}%` }}
                      />
                    </span>
                  </div>
                </Td>
              </Tr>
            );
          })}
        </TBody>
      </Table>

      <section className="mt-6 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Export — <OperationLabel operation="exportData" />
        </h2>
        <div className="space-y-3 px-4 py-3">
          <p className="text-sm text-ink-muted">
            The export projection contains the report plus every reconciliation and discrepancy in
            scope. It is derived state: exporting never changes a decision, and a superseded version
            is still present in the export.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled
              className="rounded-control border border-accent bg-accent px-3 py-1 text-2xs font-medium text-white disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-sunken disabled:text-ink-subtle"
            >
              Export JSON
            </button>
            <span className="text-2xs text-ink-subtle">
              Disabled in the skeleton build; wired during the EMM-105 data-wiring pass.
            </span>
          </div>
          <dl className="grid grid-cols-1 gap-2 text-2xs sm:grid-cols-3">
            <div>
              <dt className="text-ink-muted">report</dt>
              <dd className="mt-1 text-ink">Reconciliation counts and source watermark</dd>
            </div>
            <div>
              <dt className="text-ink-muted">reconciliations</dt>
              <dd className="mt-1 text-ink">Every decision version, including superseded</dd>
            </div>
            <div>
              <dt className="text-ink-muted">discrepancies</dt>
              <dd className="mt-1 text-ink">Open, deferred, resolved, and rejected</dd>
            </div>
          </dl>
        </div>
      </section>

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
