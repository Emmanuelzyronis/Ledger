import type { BatchState, DiscrepancyState, ErrorCode, Outcome } from "./enums";

/** Semantic tone. Maps to the `status-*` tokens in `tailwind.config.ts`. */
export type Tone = "matched" | "review" | "discrepancy" | "pending";

export const OUTCOME_TONE: Record<Outcome, Tone> = {
  MATCHED: "matched",
  MISMATCHED: "discrepancy",
  UNMATCHED_A: "review",
  UNMATCHED_B: "review",
  AMBIGUOUS: "review",
  DUPLICATE: "pending",
  INVALID: "discrepancy",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  MATCHED: "Matched",
  MISMATCHED: "Mismatched",
  UNMATCHED_A: "Unmatched A",
  UNMATCHED_B: "Unmatched B",
  AMBIGUOUS: "Ambiguous",
  DUPLICATE: "Duplicate",
  INVALID: "Invalid",
};

export const OUTCOME_MEANING: Record<Outcome, string> = {
  MATCHED: "One Source A record corresponds to exactly one Source B record.",
  MISMATCHED: "A candidate pair was found but the records do not correspond.",
  UNMATCHED_A: "Source A record had no eligible Source B candidate.",
  UNMATCHED_B: "Source B record had no eligible Source A candidate.",
  AMBIGUOUS: "More than one candidate remained; a human decision is required.",
  DUPLICATE: "The record repeats evidence already present in the batch.",
  INVALID: "Record was preserved as raw evidence but is not reconciliable.",
};

export const DISCREPANCY_STATE_TONE: Record<DiscrepancyState, Tone> = {
  OPEN: "review",
  DEFERRED: "pending",
  RESOLVED: "matched",
  REJECTED: "pending",
};

export const BATCH_STATE_TONE: Record<BatchState, Tone> = {
  RECEIVED: "pending",
  VALIDATING: "pending",
  VALIDATED: "pending",
  REJECTED: "discrepancy",
  PROCESSING: "pending",
  COMPLETED: "matched",
  PARTIAL: "review",
  FAILED: "discrepancy",
};

/** Literal utility classes so Tailwind's static extractor sees every tone. */
export const TONE_BAR_CLASS: Record<Tone, string> = {
  matched: "bg-status-matched",
  review: "bg-status-review",
  discrepancy: "bg-status-discrepancy",
  pending: "bg-status-pending",
};

/** Error codes the dashboard must render with specific operator guidance. */
export const ERROR_CODE_GUIDANCE: Partial<Record<ErrorCode | "unexpected_error", string>> = {
  authentication_required:
    "No bearer token was supplied. Set LEDGER_API_TOKEN for the frontend process.",
  invalid_token: "The bearer token was rejected. Check the token value and its expiry.",
  forbidden: "The token does not authorize this source or batch.",
  not_found: "The referenced record does not exist or is outside the token's scope.",
  rate_limited: "The service rate limit was hit. Retry after the documented window.",
  internal_error: "The service failed internally. Quote the correlation id when reporting this.",
  invalid_request: "The request body did not satisfy the contract. Check the form fields.",
  unexpected_error:
    "The service returned a response that does not match the published error contract.",
};
