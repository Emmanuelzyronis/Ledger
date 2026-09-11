import type { Metadata } from "next";
import Link from "next/link";

import { ContractCalls } from "@/components/contract-calls";
import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";
import { StatusPill } from "@/components/status-pill";
import { SummaryBand, type Stat } from "@/components/summary-band";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { PLACEHOLDER_BATCHES } from "@/lib/contract/placeholder";
import { BATCH_STATE_TONE } from "@/lib/contract/status";
import { formatCount, formatTimestamp, humanizeEnum, orDash } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Ingest Status — LEDGER" };

const CONTRACT_OPERATIONS = ["registerSource", "createBatch", "ingestRecord", "getBatch"] as const;

export default function IngestStatusPage() {
  const batches = PLACEHOLDER_BATCHES;
  const totals = batches.reduce(
    (acc, batch) => ({
      received: acc.received + batch.counters.received_count,
      accepted: acc.accepted + batch.counters.accepted_count,
      rejectedInput: acc.rejectedInput + batch.counters.rejected_input_count,
      invalid: acc.invalid + batch.counters.invalid_count,
      processed: acc.processed + batch.counters.processed_count,
    }),
    { received: 0, accepted: 0, rejectedInput: 0, invalid: 0, processed: 0 },
  );

  const stats: readonly Stat[] = [
    { label: "Batches tracked", value: formatCount(batches.length) },
    { label: "Records received", value: formatCount(totals.received) },
    { label: "Records accepted", value: formatCount(totals.accepted) },
    { label: "Rejected input", value: formatCount(totals.rejectedInput) },
    { label: "Preserved but invalid", value: formatCount(totals.invalid) },
    { label: "Processed", value: formatCount(totals.processed) },
  ];

  return (
    <>
      <PageHeader
        title="Ingest Status"
        description="Batch lifecycle and record counters per source. Raw evidence is preserved on acceptance; rejected input never disappears without an explicit state."
      />
      <PlaceholderNotice what="the batch list and counters" />
      <SummaryBand stats={stats} columns={6} />

      <Table caption="Batches">
        <THead>
          <Tr>
            <Th>Batch</Th>
            <Th>Source / schema</Th>
            <Th>State</Th>
            <Th align="right">Received</Th>
            <Th align="right">Accepted</Th>
            <Th align="right">Rejected</Th>
            <Th align="right">Invalid</Th>
            <Th align="right">Processed</Th>
            <Th>Timeline</Th>
            <Th className="w-[220px]">Error summary</Th>
          </Tr>
        </THead>
        <TBody>
          {batches.map((batch) => (
            <Tr key={batch.batch_id} accent={BATCH_STATE_TONE[batch.state]}>
              <Td className="whitespace-nowrap">
                <Link
                  href={route(`/reconciliation?batch_id=${encodeURIComponent(batch.batch_id)}`)}
                  className="font-mono text-2xs"
                >
                  {batch.batch_id}
                </Link>
                <span className="mt-[2px] block text-2xs text-ink-subtle">
                  {batch.external_batch_id}
                </span>
              </Td>
              <Td className="whitespace-nowrap">
                <span className="block font-mono text-2xs">{batch.source_id}</span>
                <span className="mt-[2px] block font-mono text-2xs text-ink-subtle">
                  {batch.schema_version}
                </span>
              </Td>
              <Td>
                <StatusPill tone={BATCH_STATE_TONE[batch.state]}>
                  {humanizeEnum(batch.state)}
                </StatusPill>
              </Td>
              <Td align="right" className="font-mono tabular-nums">
                {formatCount(batch.counters.received_count)}
              </Td>
              <Td align="right" className="font-mono tabular-nums">
                {formatCount(batch.counters.accepted_count)}
              </Td>
              <Td align="right" className="font-mono tabular-nums">
                {formatCount(batch.counters.rejected_input_count)}
              </Td>
              <Td align="right" className="font-mono tabular-nums">
                {formatCount(batch.counters.invalid_count)}
              </Td>
              <Td align="right" className="font-mono tabular-nums">
                {formatCount(batch.counters.processed_count)}
              </Td>
              <Td className="whitespace-nowrap font-mono text-2xs text-ink-muted">
                <span className="block">{formatTimestamp(batch.received_at)}</span>
                <span className="mt-[2px] block text-ink-subtle">
                  {batch.completed_at
                    ? `→ ${formatTimestamp(batch.completed_at)}`
                    : "→ not completed"}
                </span>
              </Td>
              <Td className="w-[220px] text-2xs text-ink-muted">{orDash(batch.error_summary)}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
