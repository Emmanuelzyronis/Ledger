import type { Metadata } from "next";
import Link from "next/link";

import { ContractCalls } from "@/components/contract-calls";
import { DataError } from "@/components/data-error";
import { IngestWorkflow } from "@/components/ingest-workflow";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { loadData } from "@/lib/api/server";
import { BATCH_STATE_TONE } from "@/lib/contract/status";
import { formatCount, formatTimestamp, humanizeEnum } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Ingest Status — LEDGER" };

const CONTRACT_OPERATIONS = [
  "registerSource",
  "createBatch",
  "listBatches",
  "ingestRecord",
  "getBatch",
] as const;

const TITLE = "Ingest Status";
const DESCRIPTION =
  "Register a source, create a batch, ingest source-native records, and read batch state and counters. Raw evidence is preserved on acceptance; rejected input never disappears without an explicit state.";

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

export default async function IngestStatusPage({
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
    return (
      <DataError
        title={TITLE}
        description={DESCRIPTION}
        error={list.error}
        operations={CONTRACT_OPERATIONS}
      />
    );
  }

  if (batch && !batch.ok) {
    return (
      <DataError
        title={TITLE}
        description={DESCRIPTION}
        error={batch.error}
        operations={CONTRACT_OPERATIONS}
      />
    );
  }

  const batches = list.data;
  const counters = batch?.ok ? batch.data.counters : null;
  const stats: readonly Stat[] = [
    { label: "Records received", value: counters ? formatCount(counters.received_count) : "—" },
    { label: "Accepted", value: counters ? formatCount(counters.accepted_count) : "—" },
    { label: "Rejected input", value: counters ? formatCount(counters.rejected_input_count) : "—" },
    { label: "Preserved but invalid", value: counters ? formatCount(counters.invalid_count) : "—" },
    { label: "Processed", value: counters ? formatCount(counters.processed_count) : "—" },
    { label: "Failed", value: counters ? formatCount(counters.failed_count) : "—" },
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

      <form action="/ingest" method="get" className="mb-4 flex flex-wrap items-end gap-2">
        <div>
          <label
            htmlFor="ingest-filter-source-id"
            className="block text-2xs uppercase tracking-wide text-ink-muted"
          >
            Filter by source_id
          </label>
          <input
            id="ingest-filter-source-id"
            name="source_id"
            defaultValue={sourceId ?? ""}
            placeholder="source-a"
            className="mt-1 w-64 rounded-control border border-line bg-surface px-2 py-1 font-mono text-2xs text-ink placeholder:text-ink-subtle"
          />
        </div>
        <button
          type="submit"
          className="rounded-control border border-line bg-surface-muted px-3 py-1 text-2xs font-medium text-ink"
        >
          Filter
        </button>
        {sourceId ? (
          <Link href={route("/ingest")} className="text-2xs text-accent underline">
            Clear filter
          </Link>
        ) : null}
      </form>

      <SummaryBand stats={stats} columns={6} />

      <section className="mb-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Batches{sourceId ? ` — ${sourceId}` : ""} — <span className="font-mono">listBatches</span>
        </h2>
        {batches.length ? (
          <Table caption="Batches visible to the operator">
            <THead>
              <Tr>
                <Th>Batch</Th>
                <Th>Source / schema</Th>
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
                      href={route(`/ingest?batch_id=${encodeURIComponent(row.batch_id)}`)}
                    >
                      {row.batch_id}
                    </Link>
                  </Td>
                  <Td className="font-mono text-2xs text-ink-muted">
                    {row.source_id} — {row.schema_version}
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
          <p className="px-4 py-3 text-sm text-ink-muted">
            No batches{sourceId ? ` for ${sourceId}` : ""} yet. Create one below.
          </p>
        )}
      </section>

      <section className="mb-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Batch counters
        </h2>
        {batch?.ok ? (
          <Table caption="Batch counters">
            <THead>
              <Tr>
                <Th>Counter</Th>
                <Th align="right">Value</Th>
              </Tr>
            </THead>
            <TBody>
              {COUNTERS.map(([key, label]) => (
                <Tr key={key}>
                  <Td className="font-mono text-2xs text-ink-muted">{label}</Td>
                  <Td align="right" className="font-mono tabular-nums">
                    {formatCount(batch.data.counters[key])}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            Select a batch from the list to read its state, counters, and timeline.
          </p>
        )}
      </section>

      {batch?.ok ? (
        <section className="mb-4 rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Batch {batch.data.batch_id}
          </h2>
          <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:divide-x lg:grid-cols-3">
            <div className="px-4 py-3">
              <dt className="text-2xs uppercase tracking-wide text-ink-muted">Source / schema</dt>
              <dd className="mt-1 font-mono text-2xs text-ink">
                {batch.data.source_id} — {batch.data.schema_version}
              </dd>
            </div>
            <div className="px-4 py-3">
              <dt className="text-2xs uppercase tracking-wide text-ink-muted">external_batch_id</dt>
              <dd className="mt-1 font-mono text-2xs text-ink">{batch.data.external_batch_id}</dd>
            </div>
            <div className="px-4 py-3">
              <dt className="text-2xs uppercase tracking-wide text-ink-muted">Timeline</dt>
              <dd className="mt-1 font-mono text-2xs text-ink">
                {formatTimestamp(batch.data.received_at)} →{" "}
                {formatTimestamp(batch.data.completed_at)}
              </dd>
            </div>
          </dl>
          {batch.data.error_summary ? (
            <p className="border-t border-line px-4 py-2 text-2xs text-status-discrepancy">
              {batch.data.error_summary}
            </p>
          ) : null}
        </section>
      ) : null}

      <h2 className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Ingestion operations
      </h2>
      <IngestWorkflow batchId={batch?.ok ? batch.data.batch_id : batchId} />
      <p className="mt-3 text-2xs text-ink-subtle">
        Ingestion records raw evidence only. Validation, normalization, identity, candidate
        generation, matching, and reconciliation run in the repository&rsquo;s pipeline runner; the
        v1.0 contract exposes no processing trigger, so a batch created here stays in{" "}
        <span className="font-mono">RECEIVED</span> until that runner is invoked. This is a known
        contract gap, not a silently accepted limitation.
      </p>

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
