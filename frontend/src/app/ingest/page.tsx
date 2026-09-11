import type { Metadata } from "next";

import { BatchLookupForm } from "@/components/batch-lookup-form";
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

export const metadata: Metadata = { title: "Ingest Status — LEDGER" };

const CONTRACT_OPERATIONS = ["registerSource", "createBatch", "ingestRecord", "getBatch"] as const;

const TITLE = "Ingest Status";
const DESCRIPTION =
  "Register a source, create a batch, ingest source-native records, and read a batch back by id. Raw evidence is preserved on acceptance; rejected input never disappears without an explicit state.";

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
  searchParams: Promise<{ batch_id?: string }>;
}) {
  const { batch_id: batchId } = await searchParams;
  const batch = batchId ? await loadData("getBatch", { params: { batch_id: batchId } }) : null;

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

      <BatchLookupForm action="/ingest" defaultBatchId={batchId} />
      <p className="mb-4 text-2xs text-ink-subtle">
        The published contract has no operation that enumerates batches, so a batch is addressed by
        the id returned from <span className="font-mono">POST /v1/batches</span>.
      </p>

      <SummaryBand stats={stats} columns={6} />

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
            Look up a batch id to read its state, counters, and timeline.
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
