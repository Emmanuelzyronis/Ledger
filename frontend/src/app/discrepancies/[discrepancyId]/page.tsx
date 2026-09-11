import type { Metadata } from "next";
import Link from "next/link";

import { ContractCalls } from "@/components/contract-calls";
import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";
import { ResolutionPanel } from "@/components/resolution-panel";
import { StatusPill } from "@/components/status-pill";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import {
  PLACEHOLDER_AUDIT_EVENTS,
  PLACEHOLDER_DISCREPANCIES,
  PLACEHOLDER_RECONCILIATIONS,
  PLACEHOLDER_RESOLUTION_RESULT,
} from "@/lib/contract/placeholder";
import { DISCREPANCY_STATE_TONE, OUTCOME_LABEL, OUTCOME_TONE } from "@/lib/contract/status";
import { formatTimestamp, humanizeEnum, orDash } from "@/lib/format";
import { route } from "@/lib/routes";

export const metadata: Metadata = { title: "Discrepancy — LEDGER" };

const CONTRACT_OPERATIONS = [
  "getDiscrepancy",
  "getReconciliation",
  "getAuditTrail",
  "resolveDiscrepancy",
] as const;

function Definition({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-2">
      <dt className="text-2xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}

export default async function DiscrepancyDetailPage({
  params,
}: {
  params: Promise<{ discrepancyId: string }>;
}) {
  const { discrepancyId } = await params;
  const discrepancy = PLACEHOLDER_DISCREPANCIES.find((row) => row.discrepancy_id === discrepancyId);

  if (!discrepancy) {
    return (
      <>
        <PageHeader
          title="Discrepancy not found"
          description="No discrepancy with that identifier exists in the current batch scope."
        />
        <p className="text-sm">
          <Link href={route("/discrepancies")}>Back to the discrepancy queue</Link>
        </p>
      </>
    );
  }

  const initialReconciliation = PLACEHOLDER_RECONCILIATIONS.find(
    (row) => row.reconciliation_id === discrepancy.reconciliation_id,
  );
  const resolved = PLACEHOLDER_RESOLUTION_RESULT.reconciliation;
  const superseded = initialReconciliation
    ? PLACEHOLDER_RECONCILIATIONS.find(
        (row) => row.reconciliation_id === resolved.supersedes_reconciliation_id,
      )
    : undefined;
  const auditEvents = PLACEHOLDER_AUDIT_EVENTS.filter(
    (event) => event.entity_id === discrepancy.discrepancy_id,
  );

  return (
    <>
      <PageHeader
        title={`Discrepancy ${discrepancy.discrepancy_id}`}
        description={discrepancy.reason}
        actions={
          <StatusPill tone={DISCREPANCY_STATE_TONE[discrepancy.state]}>
            {humanizeEnum(discrepancy.state)}
          </StatusPill>
        }
      />
      <PlaceholderNotice what="the evidence, audit trail, and resolution result" />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Discrepancy
          </h2>
          <dl className="divide-y divide-line">
            <Definition label="Discrepancy id">
              <span className="font-mono text-2xs">{discrepancy.discrepancy_id}</span>
            </Definition>
            <Definition label="State">
              <span className="font-mono text-2xs">{discrepancy.state}</span>
            </Definition>
            <Definition label="Reconciliation id">
              <span className="font-mono text-2xs">{discrepancy.reconciliation_id}</span>
            </Definition>
            <Definition label="Reason">{discrepancy.reason}</Definition>
          </dl>
        </section>

        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Reconciliation evidence
          </h2>
          {initialReconciliation ? (
            <>
              <dl className="divide-y divide-line">
                <Definition label="Outcome">
                  <span className="flex items-center gap-2">
                    <StatusPill
                      tone={
                        initialReconciliation.outcome
                          ? OUTCOME_TONE[initialReconciliation.outcome]
                          : "pending"
                      }
                    >
                      {initialReconciliation.outcome
                        ? OUTCOME_LABEL[initialReconciliation.outcome]
                        : "—"}
                    </StatusPill>
                    <span className="font-mono text-2xs text-ink-subtle">
                      {orDash(initialReconciliation.outcome)}
                    </span>
                  </span>
                </Definition>
                <Definition label="Rule version">
                  <span className="font-mono text-2xs">
                    {orDash(initialReconciliation.rule_version)}
                  </span>
                </Definition>
                <Definition label="Source A record">
                  <span className="font-mono text-2xs">
                    {orDash(initialReconciliation.source_a_record_id)}
                  </span>
                </Definition>
                <Definition label="Source B record">
                  <span className="font-mono text-2xs">
                    {orDash(initialReconciliation.source_b_record_id)}
                  </span>
                </Definition>
                <Definition label="Raw record">
                  <span className="font-mono text-2xs">
                    {orDash(initialReconciliation.raw_record_id)}
                  </span>
                </Definition>
              </dl>
              <div className="border-t border-line px-4 py-3">
                <p className="text-2xs uppercase tracking-wide text-ink-muted">Evidence</p>
                <pre className="mt-2 overflow-x-auto rounded-control bg-surface-sunken p-3 font-mono text-2xs text-ink">
                  {JSON.stringify(initialReconciliation.evidence, null, 2)}
                </pre>
              </div>
            </>
          ) : (
            <p className="px-4 py-3 text-sm text-ink-muted">
              No reconciliation evidence loaded for this discrepancy.
            </p>
          )}
        </section>
      </div>

      <section className="mt-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Resolution result — reconciliation version and supersession
        </h2>
        {discrepancy.state === "RESOLVED" ? (
          <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-y-0 sm:divide-x">
            <Definition label="New reconciliation version">
              <span className="font-mono tabular-nums">v{resolved.reconciliation_version}</span>
            </Definition>
            <Definition label="Supersedes">
              <span className="font-mono text-2xs">
                {orDash(resolved.supersedes_reconciliation_id)}
              </span>
            </Definition>
            <Definition label="Resolution">
              <span className="font-mono text-2xs">{resolved.resolution_id}</span>
            </Definition>
          </dl>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            No resolution recorded. This discrepancy is{" "}
            {humanizeEnum(discrepancy.state).toLowerCase()}.
          </p>
        )}
        {superseded ? (
          <div className="border-t border-line px-4 py-3 text-2xs text-ink-muted">
            Superseded v{superseded.reconciliation_version} ({superseded.reconciliation_id}) is
            retained and remains retrievable at its original version.
          </div>
        ) : null}
      </section>

      <section className="mt-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Audit trail
        </h2>
        <div className="p-4 pt-0">
          <div className="mt-4">
            <Table caption="Audit trail">
              <THead>
                <Tr>
                  <Th align="right">Seq</Th>
                  <Th>Event</Th>
                  <Th>Actor</Th>
                  <Th>Transition</Th>
                  <Th>Stage version</Th>
                  <Th>Timestamp</Th>
                  <Th>Causation event</Th>
                </Tr>
              </THead>
              <TBody>
                {auditEvents.length === 0 ? (
                  <Tr>
                    <Td colSpan={7} className="py-6 text-center text-sm text-ink-muted">
                      No audit events for this discrepancy.
                    </Td>
                  </Tr>
                ) : (
                  auditEvents.map((event) => (
                    <Tr key={event.event_id}>
                      <Td align="right" className="font-mono tabular-nums">
                        {event.sequence}
                      </Td>
                      <Td className="whitespace-nowrap font-mono text-2xs">{event.event_type}</Td>
                      <Td className="whitespace-nowrap text-2xs">{event.actor}</Td>
                      <Td className="whitespace-nowrap text-2xs text-ink-muted">
                        {`${orDash(event.previous_state)} → ${orDash(event.new_state)}`}
                      </Td>
                      <Td className="whitespace-nowrap font-mono text-2xs text-ink-muted">
                        {event.stage_version}
                      </Td>
                      <Td className="whitespace-nowrap font-mono text-2xs text-ink-muted">
                        {formatTimestamp(event.timestamp)}
                      </Td>
                      <Td className="whitespace-nowrap font-mono text-2xs text-ink-muted">
                        {orDash(event.causation_event_id)}
                      </Td>
                    </Tr>
                  ))
                )}
              </TBody>
            </Table>
          </div>
        </div>
      </section>

      <ResolutionPanel state={discrepancy.state} result={PLACEHOLDER_RESOLUTION_RESULT} />

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
