import { LedgerApiError } from "@/lib/api/client";
import { ERROR_CODE_GUIDANCE } from "@/lib/contract/status";

/** The contract's error envelope, rendered with its correlation id and guidance. */
export function LedgerErrorPanel({ error, label }: { error: LedgerApiError; label?: string }) {
  const guidance = ERROR_CODE_GUIDANCE[error.code];
  return (
    <div className="rounded-panel border border-status-discrepancy-border bg-status-discrepancy-bg px-4 py-3">
      {label ? (
        <p className="mb-2 text-2xs uppercase tracking-wide text-status-discrepancy">{label}</p>
      ) : null}
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div>
          <dt className="text-2xs uppercase tracking-wide text-ink-muted">Error code</dt>
          <dd className="mt-1 font-mono text-sm text-status-discrepancy">{error.code}</dd>
        </div>
        <div>
          <dt className="text-2xs uppercase tracking-wide text-ink-muted">HTTP status</dt>
          <dd className="mt-1 font-mono text-sm tabular-nums text-ink">
            {error.status === 0 ? "no response" : error.status}
          </dd>
        </div>
        <div>
          <dt className="text-2xs uppercase tracking-wide text-ink-muted">Correlation id</dt>
          <dd className="mt-1 font-mono text-sm text-ink">
            {error.correlationId ?? "not returned"}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-sm text-ink">{error.message}</p>
      {error.status === 0 ? (
        <p className="mt-1 text-2xs text-ink-muted">
          No response was received. Check that the service is running and that
          <span className="font-mono"> LEDGER_API_BASE_URL </span>
          points at it.
        </p>
      ) : guidance ? (
        <p className="mt-1 text-2xs text-ink-muted">{guidance}</p>
      ) : null}
    </div>
  );
}
