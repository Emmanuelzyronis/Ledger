import type { Metadata } from "next";
import Link from "next/link";

import { BatchLookupForm } from "@/components/batch-lookup-form";
import { DataError } from "@/components/data-error";
import { IdChip } from "@/components/id-chip";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import {
  OUTCOME_LABEL,
  OUTCOME_MEANING,
  OUTCOME_TONE,
  TONE_BAR_CLASS,
} from "@/lib/contract/status";
import { OUTCOMES } from "@/lib/contract/enums";
import { loadData } from "@/lib/api/server";
import { formatCount, humanizeEnum, percent } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Reconciliation — LEDGER" };

const TITLE = "Reconciliation";
const DESCRIPTION =
  "Counts by outcome for every decision version and for current versions only. A superseded version stays retrievable; it is never overwritten.";

export default async function ReconciliationPage({
  searchParams,
}: {
  searchParams: Promise<{ batch_id?: string }>;
}) {
  const { batch_id: batchId } = await searchParams;
  const query = batchId ? { batch_id: batchId } : {};

  const [report, decisions] = await Promise.all([
    loadData("getReport", { query }),
    loadData("listReconciliations", { query }),
  ]);

  if (!report.ok) {
    return <DataError title={TITLE} description={DESCRIPTION} error={report.error} />;
  }
  if (!decisions.ok) {
    return <DataError title={TITLE} description={DESCRIPTION} error={decisions.error} />;
  }

  const matched = report.data.current_outcomes.MATCHED ?? 0;
  const unmatched =
    (report.data.current_outcomes.UNMATCHED_A ?? 0) +
    (report.data.current_outcomes.UNMATCHED_B ?? 0);

  const stats: readonly Stat[] = [
    {
      label: "Reconciliation decisions",
      value: formatCount(report.data.reconciliation_count),
      detail: "all versions",
    },
    {
      label: "Current versions",
      value: formatCount(report.data.current_reconciliation_count),
      detail: "superseded excluded",
    },
    { label: "Matched", value: formatCount(matched) },
    { label: "Unmatched A + B", value: formatCount(unmatched) },
    { label: "Ambiguous", value: formatCount(report.data.current_outcomes.AMBIGUOUS ?? 0) },
    { label: "Open discrepancies", value: formatCount(report.data.discrepancy_count) },
  ];

  return (
    <>
      <PageHeader title={TITLE} description={DESCRIPTION} />

      <BatchLookupForm action="/reconciliation" defaultBatchId={batchId} />
      <p className="mb-4 text-2xs text-ink-subtle">
        {batchId ? (
          <>
            Filtered to batch <span className="font-mono">{batchId}</span>.{" "}
            <Link href={route("/reconciliation")}>Show all batches</Link>
          </>
        ) : (
          "Showing every batch. Filter by a batch id returned from the ingest screen."
        )}
      </p>

      <SummaryBand stats={stats} columns={6} />

      <h2 className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        The seven reconciliation outcomes
      </h2>
      <Table caption="Reconciliation outcomes">
        <THead>
          <Tr>
            <Th>Outcome</Th>
            <Th>Meaning</Th>
            <Th align="right">All versions</Th>
            <Th align="right">Current</Th>
            <Th>Share of current</Th>
          </Tr>
        </THead>
        <TBody>
          {OUTCOMES.map((outcome) => {
            const current = report.data.current_outcomes[outcome] ?? 0;
            const share = (current / report.data.current_reconciliation_count) * 100;
            return (
              <Tr key={outcome} accent={OUTCOME_TONE[outcome]}>
                <Td className="whitespace-nowrap">
                  <StatusPill tone={OUTCOME_TONE[outcome]}>{OUTCOME_LABEL[outcome]}</StatusPill>
                  <span className="ml-2 font-mono text-2xs text-ink-subtle">{outcome}</span>
                </Td>
                <Td className="max-w-[420px] text-2xs text-ink-muted">
                  {OUTCOME_MEANING[outcome]}
                </Td>
                <Td align="right" className="font-mono tabular-nums">
                  {formatCount(report.data.outcomes[outcome] ?? 0)}
                </Td>
                <Td align="right" className="font-mono tabular-nums">
                  {formatCount(current)}
                </Td>
                <Td className="w-[160px]">
                  <div className="flex items-center gap-3">
                    <span className="w-10 shrink-0 text-right font-mono text-2xs tabular-nums text-ink-muted">
                      {percent(current, report.data.current_reconciliation_count)}
                    </span>
                    <span className="block h-4 w-full rounded-sm bg-surface-sunken">
                      <span
                        className={`block h-4 rounded-sm ${TONE_BAR_CLASS[OUTCOME_TONE[outcome]]}`}
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

      <h2 className="mb-2 mt-6 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Decisions{batchId ? ` — batch ${batchId}` : ""}
      </h2>
      <Table caption="Reconciliation decisions">
        <THead>
          <Tr>
            <Th>ID</Th>
            <Th>Outcome</Th>
            <Th>Batch</Th>
            <Th>Records (A / B)</Th>
            <Th align="right">Version</Th>
            <Th>Supersedes</Th>
          </Tr>
        </THead>
        <TBody>
          {decisions.data.length === 0 ? (
            <Tr>
              <Td colSpan={6} className="py-6 text-center text-sm text-ink-muted">
                No reconciliation decisions in this scope.
              </Td>
            </Tr>
          ) : (
            decisions.data.map((row) => (
              <Tr
                key={row.reconciliation_id}
                accent={row.outcome ? OUTCOME_TONE[row.outcome] : "pending"}
              >
                <Td className="whitespace-nowrap">
                  <IdChip id={row.reconciliation_id} />
                </Td>
                <Td>
                  <StatusPill tone={row.outcome ? OUTCOME_TONE[row.outcome] : "pending"}>
                    {row.outcome ? OUTCOME_LABEL[row.outcome] : humanizeEnum(row.state)}
                  </StatusPill>
                </Td>
                <Td className="whitespace-nowrap">
                  <Link
                    href={route(`/reconciliation?batch_id=${encodeURIComponent(row.batch_id)}`)}
                    className="text-2xs"
                  >
                    <IdChip id={row.batch_id} />
                  </Link>
                </Td>
                <Td className="whitespace-nowrap">
                  <div className="flex flex-col gap-0.5">
                    <IdChip id={row.source_a_record_id} />
                    <IdChip id={row.source_b_record_id} />
                  </div>
                </Td>
                <Td align="right" className="font-mono tabular-nums text-2xs">
                  v{row.reconciliation_version}
                </Td>
                <Td className="whitespace-nowrap">
                  {row.supersedes_reconciliation_id ? (
                    <IdChip id={row.supersedes_reconciliation_id} />
                  ) : (
                    <span className="text-ink-subtle">—</span>
                  )}
                </Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>
    </>
  );
}
