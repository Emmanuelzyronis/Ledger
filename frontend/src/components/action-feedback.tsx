import type { ReactNode } from "react";

import type { ActionResult } from "@/lib/api/action-types";
import { LedgerApiError } from "@/lib/api/client";

import { LedgerErrorPanel } from "./error-panel";

/**
 * Renders a server action's result. A contract error keeps its code, status, and
 * correlation id so the operator can quote them; a success is stated plainly.
 */
export function ActionFeedback<T>({
  result,
  children,
}: {
  result: ActionResult<T> | null;
  children: (data: T) => ReactNode;
}) {
  if (!result) return null;
  if (!result.ok) {
    return (
      <div className="mt-3">
        <LedgerErrorPanel
          error={
            new LedgerApiError(
              result.status,
              result.code,
              result.message,
              result.correlationId,
              undefined,
            )
          }
        />
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-control border border-status-matched-border bg-status-matched-bg px-3 py-2">
      <p className="text-2xs uppercase tracking-wide text-status-matched">Recorded</p>
      <div className="mt-1 space-y-1 text-2xs text-ink">{children(result.data)}</div>
      {result.correlationId ? (
        <p className="mt-1 font-mono text-2xs text-ink-subtle">
          correlation_id {result.correlationId}
        </p>
      ) : null}
    </div>
  );
}
