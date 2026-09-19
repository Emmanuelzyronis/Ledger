import type { Metadata } from "next";
import Link from "next/link";

import { DataError } from "@/components/data-error";
import { IdChip } from "@/components/id-chip";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { loadData } from "@/lib/api/server";
import { BATCH_STATE_TONE } from "@/lib/contract/status";
import { formatCount, formatTimestamp, humanizeEnum } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Batches — LEDGER" };

const TITLE = "Batches";
const DESCRIPTION =
  "All ingestion batches visible to this operator. Select a batch to view its counters and processing timeline.";

const COUNTERS = [
  ["received_count", "Received"],
  ["accepted_count", "Accepted"],
  ["rejected_input_count", "Rejected input"],
  ["invalid_count", "Preserved but invalid"],
  ["processed_count", "Processed"],
  ["matched_count", "Matched"],
  ["mismatched_count", "Mismatched"],
  ["unmatched_count", "Unmatched"],
  ["ambiguous_count", "Ambiguous"],
  ["duplicate_count", "Duplicate"],
  ["failed_count", "Failed"],
] as const;

export default async function BatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ batch_id?: string; source_id?: string }>;
}) {
  const { batch_id: batchId, source_id: sourceId } = await searchParams;
  const [list, batch] = await Promise.all([
    loadData("listBatches", sourceId ? { query: { source_id: sourceId } } : undefined),
    batchId ? loadData("getBatch", { params: { batch_id: batchId } }) : Promise.resolve(null),
  ]);

  if (!list.ok) {
    return <DataError title={TITLE} description={DESCRIPTION} error={list.error} />;
  }
  if (batch && !batch.ok) {
    return <DataError title={TITLE} description={DESCRIPTION} error={batch.error} />;
  }

  const batches = list.data;
  const completed = batches.filter((b) => b.state === "COMPLETED").length;
  const failed = batches.filter((b) => b.state === "FAILED").length;
  const processing = batches.filter(
    (b) => b.state === "PROCESSING" || b.state === "VALIDATING",
  ).length;

  const counters = batch?.ok ? batch.data.counters : null;
  const stats: readonly Stat[] = [
    { label: "Total batches", value: formatCount(batches.length) },
    { label: "Completed", value: formatCount(completed) },
    { label: "Processing", value: formatCount(processing) },
    { label: "Failed", value: formatCount(failed) },
    { label: "Records received", value: counters ? formatCount(counters.received_count) : "—" },
    { label: "Matched", value: counters ? formatCount(counters.matched_count) : "—" },
  ];

  return (
    <>
      <PageHeader
        title={TITLE}
        description={DESCRIPTION}
        actions={
          batch?.ok ? (
            <StatusPill tone={BATCH_STATE_TONE[batch.data.state]}>
              {humanizeEnum(batch.data.state)}
            </StatusPill>
          ) : undefined
        }
      />

      <form action="/batches" method="get" className="mb-4 flex flex-wrap items-end gap-2">
        <div>
          <label
            htmlFor="batches-filter-source"
            className="block text-2xs uppercase tracking-wide text-ink-muted"
          >
            Filter by source
          </label>
          <input
            id="batches-filter-source"
            name="source_id"
            defaultValue={sourceId ?? ""}
            placeholder="source-a"
            className="mt-1 w-48 rounded-control border border-line bg-surface px-2 py-1 font-mono text-2xs text-ink placeholder:text-ink-subtle"
          />
        </div>
        <button
          type="submit"
          className="rounded-control border border-line bg-surface-muted px-3 py-1 text-2xs font-medium text-ink"
        >
          Filter
        </button>
        {sourceId ? (
          <Link href={route("/batches")} className="text-2xs text-accent underline">
            Clear
          </Link>
        ) : null}
      </form>

      <SummaryBand stats={stats} columns={6} />

      <section className="mb-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          {sourceId ? `Batches — ${sourceId}` : "All batches"}
        </h2>
        {batches.length ? (
          <Table caption="Batches">
            <THead>
              <Tr>
                <Th>Batch ID</Th>
                <Th>Source</Th>
                <Th>State</Th>
                <Th>Received</Th>
                <Th align="right">Records</Th>
              </Tr>
            </THead>
            <TBody>
              {batches.map((row) => (
                <Tr key={row.batch_id}>
                  <Td>
                    <Link
                      className="font-mono text-2xs text-accent underline"
                      href={route(`/batches?batch_id=${encodeURIComponent(row.batch_id)}`)}
                    >
                      <IdChip id={row.batch_id} />
                    </Link>
                  </Td>
                  <Td className="font-mono text-2xs text-ink-muted">
                    {row.source_id}
                    <span className="ml-2 text-ink-subtle">{row.schema_version}</span>
                  </Td>
                  <Td>
                    <StatusPill tone={BATCH_STATE_TONE[row.state]}>
                      {humanizeEnum(row.state)}
                    </StatusPill>
                  </Td>
                  <Td className="font-mono text-2xs text-ink-muted">
                    {formatTimestamp(row.received_at)}
                  </Td>
                  <Td align="right" className="font-mono tabular-nums">
                    {formatCount(row.counters.received_count)}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-ink-muted">
            No batches{sourceId ? ` for source ${sourceId}` : ""}.
          </p>
        )}
      </section>

      {batch?.ok ? (
        <>
          <section className="mb-4 rounded-panel border border-line bg-surface">
            <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
              Batch detail
            </h2>
            <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-3">
              <div className="px-4 py-3">
                <dt className="text-2xs uppercase tracking-wide text-ink-muted">Batch ID</dt>
                <dd className="mt-1 font-mono text-2xs text-ink">
                  <IdChip id={batch.data.batch_id} hexLen={12} />
                </dd>
              </div>
              <div className="px-4 py-3">
                <dt className="text-2xs uppercase tracking-wide text-ink-muted">Source / schema</dt>
                <dd className="mt-1 font-mono text-2xs text-ink">
                  {batch.data.source_id} — {batch.data.schema_version}
                </dd>
              </div>
              <div className="px-4 py-3">
                <dt className="text-2xs uppercase tracking-wide text-ink-muted">Timeline</dt>
                <dd className="mt-1 font-mono text-2xs text-ink">
                  {formatTimestamp(batch.data.received_at)}
                  {batch.data.completed_at ? ` → ${formatTimestamp(batch.data.completed_at)}` : ""}
                </dd>
              </div>
            </dl>
            {batch.data.error_summary ? (
              <p className="border-t border-line px-4 py-2 text-2xs text-status-discrepancy">
                {batch.data.error_summary}
              </p>
            ) : null}
          </section>

          <section className="mb-4 rounded-panel border border-line bg-surface">
            <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
              Counters
            </h2>
            <div className="grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-4 lg:grid-cols-6">
              {COUNTERS.map(([key, label]) => (
                <div key={key} className="px-4 py-3">
                  <p className="text-2xs text-ink-muted">{label}</p>
                  <p className="mt-1 font-mono tabular-nums text-sm font-medium text-ink">
                    {formatCount(batch.data.counters[key])}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <p className="text-2xs text-ink-subtle">Select a batch from the list to view counters.</p>
      )}
    </>
  );
}
