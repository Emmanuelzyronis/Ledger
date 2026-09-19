import type { Metadata } from "next";
import Link from "next/link";

import { DataError } from "@/components/data-error";
import { IdChip } from "@/components/id-chip";
import { PageHeader } from "@/components/page-header";
import { ResolutionPanel } from "@/components/resolution-panel";
import { StatusPill } from "@/components/status-pill";
import { loadData } from "@/lib/api/server";
import { DISCREPANCY_STATE_TONE, OUTCOME_LABEL, OUTCOME_TONE } from "@/lib/contract/status";
import { formatTimestamp, humanizeEnum, orDash } from "@/lib/format";
import { decodeRouteParam, route } from "@/lib/routes";

export const metadata: Metadata = { title: "Exception — LEDGER" };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <dt className="text-2xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}

export default async function ExceptionDetailPage({
  params,
}: {
  params: Promise<{ exceptionId: string }>;
}) {
  const { exceptionId } = await params;
  const id = decodeRouteParam(exceptionId);
  const discrepancy = await loadData("getDiscrepancy", {
    params: { discrepancy_id: id },
  });

  if (!discrepancy.ok) {
    if (discrepancy.error.code === "not_found") {
      return (
        <>
          <PageHeader
            title="Exception not found"
            description="No exception with that identifier exists in the current source scope."
          />
          <Link href={route("/exceptions")}>Back to exceptions</Link>
        </>
      );
    }
    return (
      <DataError
        title={`Exception ${id}`}
        description="The exception could not be read from the service."
        error={discrepancy.error}
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

  const successor =
    reconciliation.ok && successors?.ok
      ? (successors.data
          .filter(
            (row) => row.supersedes_reconciliation_id === reconciliation.data.reconciliation_id,
          )
          .sort((a, b) => b.reconciliation_version - a.reconciliation_version)[0] ?? null)
      : null;

  const isOpen = discrepancy.data.state === "OPEN";

  return (
    <>
      <PageHeader
        title={`Exception`}
        description={discrepancy.data.reason}
        actions={
          <div className="flex items-center gap-3">
            <StatusPill tone={DISCREPANCY_STATE_TONE[discrepancy.data.state]}>
              {humanizeEnum(discrepancy.data.state)}
            </StatusPill>
            <Link href={route("/exceptions")} className="text-2xs text-ink-muted">
              ← All exceptions
            </Link>
          </div>
        }
      />

      <div className="mb-1 font-mono text-2xs text-ink-subtle">
        <IdChip id={discrepancy.data.discrepancy_id} hexLen={12} />
      </div>

      {/* Resolution form — prominent at top for OPEN exceptions */}
      {isOpen ? (
        <div className="mb-6">
          <ResolutionPanel
            discrepancyId={discrepancy.data.discrepancy_id}
            state={discrepancy.data.state}
          />
        </div>
      ) : null}

      {/* Evidence — two-column side-by-side */}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Exception
          </h2>
          <dl className="divide-y divide-line">
            <Field label="State">
              <StatusPill tone={DISCREPANCY_STATE_TONE[discrepancy.data.state]}>
                {humanizeEnum(discrepancy.data.state)}
              </StatusPill>
            </Field>
            <Field label="Reason">{discrepancy.data.reason}</Field>
            <Field label="Exception ID">
              <span className="font-mono text-2xs">
                <IdChip id={discrepancy.data.discrepancy_id} hexLen={16} />
              </span>
            </Field>
            <Field label="Reconciliation">
              <IdChip id={discrepancy.data.reconciliation_id} />
            </Field>
          </dl>
        </section>

        <section className="rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Reconciliation decision
          </h2>
          {reconciliation.ok ? (
            <dl className="divide-y divide-line">
              <Field label="Outcome">
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
                </span>
              </Field>
              <Field label="Version">
                <span className="font-mono">v{reconciliation.data.reconciliation_version}</span>
              </Field>
              <Field label="Rule version">
                <span className="font-mono text-2xs">{orDash(reconciliation.data.rule_version)}</span>
              </Field>
              <Field label="Source A record">
                <IdChip id={reconciliation.data.source_a_record_id} />
              </Field>
              <Field label="Source B record">
                <IdChip id={reconciliation.data.source_b_record_id} />
              </Field>
              {reconciliation.data.evidence &&
              Object.keys(reconciliation.data.evidence).length > 0 ? (
                <div className="px-4 py-3">
                  <details className="text-2xs">
                    <summary className="cursor-pointer text-ink-muted hover:text-ink">
                      Show raw evidence
                    </summary>
                    <pre className="mt-2 overflow-x-auto rounded-control bg-surface-sunken p-3 font-mono text-ink">
                      {JSON.stringify(reconciliation.data.evidence, null, 2)}
                    </pre>
                  </details>
                </div>
              ) : null}
            </dl>
          ) : (
            <p className="px-4 py-3 text-sm text-ink-muted">
              Reconciliation evidence unavailable.
            </p>
          )}
        </section>
      </div>

      {/* Supersession result (after resolution) */}
      {successor ? (
        <section className="mt-4 rounded-panel border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
            Resolution outcome
          </h2>
          <dl className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-y-0 sm:divide-x">
            <Field label="New version">
              <span className="font-mono">v{successor.reconciliation_version}</span>
            </Field>
            <Field label="Supersedes">
              <IdChip id={successor.supersedes_reconciliation_id} />
            </Field>
            <Field label="Resolution ID">
              <IdChip id={successor.resolution_id} />
            </Field>
          </dl>
          {reconciliation.ok ? (
            <p className="border-t border-line px-4 py-2 text-2xs text-ink-subtle">
              Original v{reconciliation.data.reconciliation_version} (
              <IdChip id={reconciliation.data.reconciliation_id} />) is retained immutably.
            </p>
          ) : null}
        </section>
      ) : null}

      {/* Resolution form for non-open state (informational) */}
      {!isOpen ? (
        <div className="mt-4">
          <ResolutionPanel
            discrepancyId={discrepancy.data.discrepancy_id}
            state={discrepancy.data.state}
          />
        </div>
      ) : null}

      {/* Audit timeline */}
      <section className="mt-4 rounded-panel border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
          Audit trail
        </h2>
        {audit.ok && audit.data.length > 0 ? (
          <ol className="divide-y divide-line">
            {audit.data.map((event) => (
              <li key={event.event_id} className="flex items-start gap-4 px-4 py-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-sunken font-mono text-[10px] text-ink-muted">
                  {event.sequence}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-2xs">
                    <span className="font-medium text-ink">{event.event_type}</span>
                    <span className="text-ink-muted">by {event.actor}</span>
                    {event.previous_state || event.new_state ? (
                      <span className="font-mono text-ink-subtle">
                        {orDash(event.previous_state)} → {orDash(event.new_state)}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 font-mono text-[11px] text-ink-subtle">
                    {formatTimestamp(event.timestamp)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        ) : audit.ok ? (
          <p className="px-4 py-3 text-sm text-ink-muted">No audit events recorded.</p>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            Audit trail unavailable: {audit.error.message}
          </p>
        )}
      </section>
    </>
  );
}
