import type { ReactNode } from "react";

import type { Tone } from "@/lib/contract/status";

const PILL: Record<Tone, string> = {
  matched: "border-status-matched-border bg-status-matched-bg text-status-matched",
  review: "border-status-review-border bg-status-review-bg text-status-review",
  discrepancy: "border-status-discrepancy-border bg-status-discrepancy-bg text-status-discrepancy",
  pending: "border-status-pending-border bg-status-pending-bg text-status-pending",
};

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2 py-[2px] text-2xs font-medium ${PILL[tone]}`}
    >
      {children}
    </span>
  );
}
