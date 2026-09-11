"use client";

import { useState } from "react";

import { LedgerApiError } from "@/lib/api/client";
import { RESOLUTION_TYPES, type DiscrepancyState } from "@/lib/contract/enums";
import type { components } from "@/lib/api/schema";
import { humanizeEnum } from "@/lib/format";

import { LedgerErrorPanel } from "./error-panel";
import { OperationLabel } from "./operation-label";

const SAMPLE_ERROR = new LedgerApiError(
  500,
  "internal_error",
  "The service failed while recording the resolution.",
  "corr-7d2f80aa91c4de10",
  undefined,
);

export function ResolutionPanel({
  state,
  result,
}: {
  state: DiscrepancyState;
  result: components["schemas"]["ResolutionResult"];
}) {
  const [resolutionType, setResolutionType] =
    useState<(typeof RESOLUTION_TYPES)[number]>("MANUAL_APPROVED");
  const [reason, setReason] = useState("");
  const open = state === "OPEN";

  return (
    <section className="mt-4 rounded-panel border border-line bg-surface">
      <h2 className="border-b border-line px-4 py-2 text-2xs font-medium uppercase tracking-wide text-ink-muted">
        Resolution action — <OperationLabel operation="resolveDiscrepancy" />
      </h2>
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        <form className="space-y-3" onSubmit={(event) => event.preventDefault()}>
          <div>
            <label
              htmlFor="resolution_type"
              className="block text-2xs uppercase tracking-wide text-ink-muted"
            >
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
              className="mt-1 w-full rounded-control border border-line bg-surface px-2 py-1 font-mono text-2xs text-ink disabled:bg-surface-sunken disabled:text-ink-subtle"
            >
              {RESOLUTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type} — {humanizeEnum(type)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="reason"
              className="block text-2xs uppercase tracking-wide text-ink-muted"
            >
              Reason (required)
            </label>
            <textarea
              id="reason"
              name="reason"
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={!open}
              placeholder="Operator justification recorded immutably with the resolution."
              className="mt-1 w-full rounded-control border border-line bg-surface px-2 py-1 text-sm text-ink placeholder:text-ink-subtle disabled:bg-surface-sunken"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled
              className="rounded-control border border-accent bg-accent px-3 py-1 text-2xs font-medium text-white disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-sunken disabled:text-ink-subtle"
            >
              Record resolution
            </button>
            <span className="text-2xs text-ink-subtle">
              {open
                ? "Disabled in the skeleton build; wired during the EMM-105 data-wiring pass."
                : `This discrepancy is ${humanizeEnum(state).toLowerCase()}; only OPEN discrepancies can be resolved.`}
            </span>
          </div>
        </form>

        <div className="space-y-3">
          <div className="rounded-panel border border-line bg-surface-muted px-4 py-3">
            <p className="text-2xs uppercase tracking-wide text-ink-muted">
              On success — ResolutionResult
            </p>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-2xs">
              <div>
                <dt className="text-ink-muted">resolution_id</dt>
                <dd className="mt-1 font-mono text-ink">{result.resolution.resolution_id}</dd>
              </div>
              <div>
                <dt className="text-ink-muted">reconciliation_version</dt>
                <dd className="mt-1 font-mono tabular-nums text-ink">
                  v{result.reconciliation.reconciliation_version}
                </dd>
              </div>
              <div>
                <dt className="text-ink-muted">supersedes_reconciliation_id</dt>
                <dd className="mt-1 font-mono text-ink">
                  {result.reconciliation.supersedes_reconciliation_id ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-ink-muted">discrepancy.state</dt>
                <dd className="mt-1 font-mono text-ink">{result.discrepancy.state}</dd>
              </div>
            </dl>
          </div>
          <LedgerErrorPanel
            error={SAMPLE_ERROR}
            label="Sample: contract error surface (not a live failure)"
          />
        </div>
      </div>
    </section>
  );
}
