import type { Metadata } from "next";
import Link from "next/link";

import { ContractCalls } from "@/components/contract-calls";
import { DataError } from "@/components/data-error";
import { PageHeader } from "@/components/page-header";
import { ResolutionPanel } from "@/components/resolution-panel";
import { StatusPill } from "@/components/status-pill";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/table";
import { loadData } from "@/lib/api/server";
import { DISCREPANCY_STATE_TONE, OUTCOME_LABEL, OUTCOME_TONE } from "@/lib/contract/status";
import { formatTimestamp, humanizeEnum, orDash } from "@/lib/format";
import { decodeRouteParam, route } from "@/lib/routes";

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
  const id = decodeRouteParam(discrepancyId);
  const discrepancy = await loadData("getDiscrepancy", {
    params: { discrepancy_id: id },
  });

  if (!discrepancy.ok) {
    if (discrepancy.error.code === "not_found") {
      return (
        <>
          <PageHeader
            title="Discrepancy not found"
            description="No discrepancy with that identifier exists in the current source scope."
          />
          <p className="text-sm">
            <Link href={route("/discrepancies")}>Back to the discrepancy queue</Link>
          </p>
        </>
      );
    }
    return (
      <DataError
        title={`Discrepancy ${id}`}
        description="The discrepancy could not be read from the service."
        error={discrepancy.error}
        operations={CONTRACT_OPERATIONS}
      />
    );
  }

  const [reconciliation, audit] = await Promise.all([
    loadData("getReconciliation", {
      params: { reconciliation_id: discrepancy.data.reconciliation_id },
    }),
    loadData("getAuditTrail", {
      params: { entity_type: "discrepancy", entity_id: id },
    }),
  ]);

  const successors = reconciliation.ok
    ? await loadData("listReconciliations", { query: { batch_id: reconciliation.data.batch_id } })
    : null;

  // The newest decision that supersedes this one. Nothing is overwritten, so the
  // superseded version stays retrievable at its original size and id.
  const successor =
    reconciliation.ok && successors?.ok
      ? (successors.data
          .filter(
            (row) => row.supersedes_reconciliation_id === reconciliation.data.reconciliation_id,
          )
          .sort((a, b) => b.reconciliation_version - a.reconciliation_version)[0] ?? null)
      : null;

  return (
    <>
      <PageHeader
        title={`Discrepancy ${discrepancy.data.discrepancy_id}`}
        description={discrepancy.data.reason}
        actions={
          <StatusPill tone={DISCREPANCY_STATE_TONE[discrepancy.data.state]}>
            {humanizeEnum(discrepancy.data.state)}
          </StatusPill>
        }
      />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Discrepancy
          </h2>
          <dl className="divide-y divide-line">
            <Definition label="Discrepancy id">
              <span className="font-mono text-2xs">{discrepancy.data.discrepancy_id}</span>
            </Definition>
            <Definition label="State">
              <span className="font-mono text-2xs">{discrepancy.data.state}</span>
            </Definition>
            <Definition label="Reconciliation id">
              <span className="font-mono text-2xs">{discrepancy.data.reconciliation_id}</span>
            </Definition>
            <Definition label="Reason">{discrepancy.data.reason}</Definition>
          </dl>
        </section>

        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Reconciliation evidence
          </h2>
          {reconciliation.ok ? (
            <>
              <dl className="divide-y divide-line">
                <Definition label="Outcome">
                  <span className="flex items-center gap-2">
                    <StatusPill
                      tone={
                        reconciliation.data.outcome
                          ? OUTCOME_TONE[reconciliation.data.outcome]
                          : "pending"
                      }
                    >
                      {reconciliation.data.outcome
                        ? OUTCOME_LABEL[reconciliation.data.outcome]
                        : "—"}
                    </StatusPill>
                    <span className="font-mono text-2xs text-ink-subtle">
                      {orDash(reconciliation.data.outcome)}
                    </span>
                  </span>
                </Definition>
                <Definition label="Rule version">
                  <span className="font-mono text-2xs">
                    {orDash(reconciliation.data.rule_version)}
                  </span>
                </Definition>
                <Definition label="Reconciliation version">
                  <span className="font-mono tabular-nums">
                    v{reconciliation.data.reconciliation_version}
                  </span>
                </Definition>
                <Definition label="Source A record">
                  <span className="font-mono text-2xs">
                    {orDash(reconciliation.data.source_a_record_id)}
                  </span>
                </Definition>
                <Definition label="Source B record">
                  <span className="font-mono text-2xs">
                    {orDash(reconciliation.data.source_b_record_id)}
                  </span>
                </Definition>
                <Definition label="Raw record">
                  <span className="font-mono text-2xs">
                    {orDash(reconciliation.data.raw_record_id)}
                  </span>
                </Definition>
              </dl>
              <div className="border-t border-line px-4 py-3">
                <p className="text-2xs uppercase tracking-wide text-ink-muted">Evidence</p>
                <pre className="mt-2 overflow-x-auto rounded-control bg-surface-sunken p-3 font-mono text-2xs text-ink">
                  {JSON.stringify(reconciliation.data.evidence, null, 2)}
                </pre>
              </div>
            </>
          ) : (
            <p className="px-4 py-3 text-sm text-ink-muted">
              Reconciliation evidence is unavailable: {reconciliation.error.message}
            </p>
          )}
        </section>
      </div>

      <section className="mt-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Resolution result — reconciliation version and supersession
        </h2>
        {successor ? (
          <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-y-0 sm:divide-x">
            <Definition label="New reconciliation version">
              <span className="font-mono tabular-nums">v{successor.reconciliation_version}</span>
            </Definition>
            <Definition label="Supersedes">
              <span className="font-mono text-2xs">
                {orDash(successor.supersedes_reconciliation_id)}
              </span>
            </Definition>
            <Definition label="Resolution">
              <span className="font-mono text-2xs">{orDash(successor.resolution_id)}</span>
            </Definition>
          </dl>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            {discrepancy.data.state === "RESOLVED"
              ? "This discrepancy is resolved; the superseding decision is not in the current read scope."
              : `No resolution recorded. This discrepancy is ${humanizeEnum(discrepancy.data.state).toLowerCase()}.`}
          </p>
        )}
        {reconciliation.ok && successor ? (
          <div className="border-t border-line px-4 py-3 text-2xs text-ink-muted">
            Superseded v{reconciliation.data.reconciliation_version} (
            <span className="font-mono">{reconciliation.data.reconciliation_id}</span>) is retained
            and remains retrievable at its original version.
          </div>
        ) : null}
      </section>

      <section className="mt-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Audit trail
        </h2>
        {audit.ok ? (
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
                {audit.data.length === 0 ? (
                  <Tr>
                    <Td colSpan={7} className="py-6 text-center text-sm text-ink-muted">
                      No audit events for this discrepancy.
                    </Td>
                  </Tr>
                ) : (
                  audit.data.map((event) => (
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
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            Audit trail unavailable: {audit.error.message}
          </p>
        )}
      </section>

      <ResolutionPanel
        discrepancyId={discrepancy.data.discrepancy_id}
        state={discrepancy.data.state}
      />

      <ContractCalls operations={CONTRACT_OPERATIONS} />
    </>
  );
}
