"use client";

import { useActionState, useState } from "react";

import { ActionFeedback } from "@/components/action-feedback";
import { resolveDiscrepancyAction } from "@/lib/api/actions";
import type { components } from "@/lib/api/schema";
import { RESOLUTION_TYPES } from "@/lib/contract/enums";
import { humanizeEnum } from "@/lib/format";

const INPUT =
  "mt-1 w-full rounded-control border border-line bg-surface px-2 py-1 text-sm text-ink placeholder:text-ink-subtle disabled:bg-surface-sunken disabled:text-ink-subtle";
const LABEL = "block text-2xs uppercase tracking-wide text-ink-muted";

/**
 * The one mutation the dashboard performs. It names `resolveDiscrepancy`, posts
 * through a server action so the bearer token stays server-side, and renders the
 * returned `ResolutionResult` — including the new reconciliation version and the
 * id of the version it supersedes.
 */
export function ResolutionPanel({
  discrepancyId,
  state,
}: {
  discrepancyId: string;
  state: components["schemas"]["Discrepancy"]["state"];
}) {
  const [resolutionType, setResolutionType] =
    useState<(typeof RESOLUTION_TYPES)[number]>("MANUAL_APPROVED");
  const [reason, setReason] = useState("");
  const [result, submit, pending] = useActionState(resolveDiscrepancyAction, null);
  const open = state === "OPEN";

  return (
    <section className="mt-4 rounded-panel border border-line bg-surface">
      <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Resolution action —{" "}
        <span className="font-mono">POST /v1/discrepancies/{"{id}"}/resolve</span>
      </h2>
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        <form action={submit} className="space-y-3">
          <input type="hidden" name="discrepancy_id" value={discrepancyId} />
          <div>
            <label htmlFor="resolution_type" className={LABEL}>
              Resolution type
            </label>
            <select
              id="resolution_type"
              name="resolution_type"
              value={resolutionType}
              onChange={(event) =>
                setResolutionType(event.target.value as (typeof RESOLUTION_TYPES)[number])
              }
              disabled={!open}
              className={`${INPUT} font-mono text-2xs`}
            >
              {RESOLUTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type} — {humanizeEnum(type)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="reason" className={LABEL}>
              Reason (required, recorded immutably)
            </label>
            <textarea
              id="reason"
              name="reason"
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={!open}
              placeholder="Operator justification recorded immutably with the resolution."
              className={INPUT}
            />
          </div>
          <div>
            <label htmlFor="evidence" className={LABEL}>
              Evidence JSON (optional)
            </label>
            <textarea
              id="evidence"
              name="evidence"
              rows={2}
              disabled={!open}
              placeholder='{"operator_note":"receipt reference R-8891"}'
              className={`${INPUT} font-mono text-2xs`}
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!open || pending || reason.trim().length === 0}
              className="rounded-control border border-accent bg-accent px-3 py-1 text-2xs font-medium text-white disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-sunken disabled:text-ink-subtle"
            >
              {pending ? "Recording…" : "Record resolution"}
            </button>
            <span className="text-2xs text-ink-subtle">
              {open
                ? "Resolving opens a new reconciliation version; the superseded version is retained."
                : `This discrepancy is ${humanizeEnum(state).toLowerCase()}; only OPEN discrepancies can be resolved.`}
            </span>
          </div>
        </form>

        <div className="space-y-3">
          <div className="rounded-panel border border-line bg-surface-muted px-4 py-3">
            <p className="text-2xs uppercase tracking-wide text-ink-muted">
              {result?.ok ? "Recorded — ResolutionResult" : "On success — ResolutionResult"}
            </p>
            {result?.ok ? (
              <dl className="mt-2 grid grid-cols-2 gap-2 text-2xs">
                <div>
                  <dt className="text-ink-muted">resolution_id</dt>
                  <dd className="mt-1 font-mono text-ink">
                    {result.data.resolution.resolution_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">reconciliation_version</dt>
                  <dd className="mt-1 font-mono tabular-nums text-ink">
                    v{result.data.reconciliation.reconciliation_version}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">supersedes_reconciliation_id</dt>
                  <dd className="mt-1 font-mono text-ink">
                    {result.data.reconciliation.supersedes_reconciliation_id ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">discrepancy.state</dt>
                  <dd className="mt-1 font-mono text-ink">{result.data.discrepancy.state}</dd>
                </div>
              </dl>
            ) : (
              <p className="mt-2 text-2xs text-ink-muted">
                The returned resolution, the new reconciliation version, its supersession link, and
                the discrepancy&rsquo;s new state.
              </p>
            )}
          </div>
          <ActionFeedback result={result}>
            {(data) => <p>Resolution {data.resolution.resolution_id} recorded.</p>}
          </ActionFeedback>
        </div>
      </div>
    </section>
  );
}
