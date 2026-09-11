import type { components } from "@/lib/api/schema";

/**
 * PLACEHOLDER DATA — skeleton pass only.
 *
 * These fixtures exist so the visual direction and information architecture can
 * be reviewed before the EMM-105 data-wiring pass. Nothing here is fetched from
 * the service, and every value is shaped by the generated contract types, so a
 * contract change breaks the build instead of silently diverging.
 */

type Batch = components["schemas"]["Batch"];
type Report = components["schemas"]["Report"];
type Reconciliation = components["schemas"]["Reconciliation"];
type Discrepancy = components["schemas"]["Discrepancy"];
type AuditEvent = components["schemas"]["AuditEvent"];
type ResolutionResult = components["schemas"]["ResolutionResult"];

const D = (iso: string): string => iso;

export const PLACEHOLDER_BATCHES: readonly Batch[] = [
  {
    batch_id: "batch-201",
    source_id: "source-a",
    external_batch_id: "A-2026-09-08-settlement",
    schema_version: "source_a.v1",
    received_at: D("2026-09-08T06:00:04Z"),
    state: "COMPLETED",
    counters: {
      received_count: 1250,
      accepted_count: 1247,
      rejected_input_count: 3,
      invalid_count: 2,
      processed_count: 1245,
      matched_count: 1180,
      mismatched_count: 24,
      unmatched_count: 33,
      ambiguous_count: 6,
      duplicate_count: 2,
      failed_count: 0,
    },
    started_at: D("2026-09-08T06:00:04Z"),
    completed_at: D("2026-09-08T06:03:41Z"),
    error_summary: null,
  },
  {
    batch_id: "batch-202",
    source_id: "source-b",
    external_batch_id: "B-2026-09-08-settlement",
    schema_version: "source_b.v1",
    received_at: D("2026-09-08T06:00:07Z"),
    state: "PARTIAL",
    counters: {
      received_count: 1249,
      accepted_count: 1240,
      rejected_input_count: 4,
      invalid_count: 5,
      processed_count: 1236,
      matched_count: 1180,
      mismatched_count: 24,
      unmatched_count: 27,
      ambiguous_count: 6,
      duplicate_count: 1,
      failed_count: 2,
    },
    started_at: D("2026-09-08T06:00:07Z"),
    completed_at: D("2026-09-08T06:05:12Z"),
    error_summary: "2 records failed normalization: unsupported currency.",
  },
  {
    batch_id: "batch-203",
    source_id: "source-a",
    external_batch_id: "A-2026-09-09-intraday",
    schema_version: "source_a.v1",
    received_at: D("2026-09-09T13:22:18Z"),
    state: "RECEIVED",
    counters: {
      received_count: 318,
      accepted_count: 0,
      rejected_input_count: 0,
      invalid_count: 0,
      processed_count: 0,
      matched_count: 0,
      mismatched_count: 0,
      unmatched_count: 0,
      ambiguous_count: 0,
      duplicate_count: 0,
      failed_count: 0,
    },
    started_at: null,
    completed_at: null,
    error_summary: null,
  },
];

export const PLACEHOLDER_REPORT: Report = {
  batch_id: "batch-201",
  reconciliation_count: 1245,
  outcomes: {
    MATCHED: 1180,
    MISMATCHED: 24,
    UNMATCHED_A: 20,
    UNMATCHED_B: 13,
    AMBIGUOUS: 6,
    DUPLICATE: 2,
    INVALID: 0,
  },
  current_reconciliation_count: 1243,
  current_outcomes: {
    MATCHED: 1180,
    MISMATCHED: 24,
    UNMATCHED_A: 20,
    UNMATCHED_B: 13,
    AMBIGUOUS: 4,
    DUPLICATE: 2,
    INVALID: 0,
  },
  discrepancy_count: 67,
  source_watermark: {
    event_count: 2499,
    timestamp: D("2026-09-08T06:05:12Z"),
  },
};

export const PLACEHOLDER_RECONCILIATIONS: readonly Reconciliation[] = [
  {
    reconciliation_id: "rec-0001",
    batch_id: "batch-201",
    source_a_record_id: "src-A00117",
    source_b_record_id: "src-B00119",
    raw_record_id: "raw:source-a:source_a.v1:a01bb22d",
    reconciliation_version: 1,
    rule_version: "match.v1",
    evidence: {
      amount_delta: "0.00",
      currency: "USD",
      occurred_at_delta_days: 0,
      candidate_count: 1,
    },
    state: "MATCHED",
    outcome: "MATCHED",
    supersedes_reconciliation_id: null,
    resolution_id: null,
  },
  {
    reconciliation_id: "rec-0198",
    batch_id: "batch-201",
    source_a_record_id: "src-A00402",
    source_b_record_id: "src-B00404",
    raw_record_id: "raw:source-b:source_b.v1:7d2f80aa",
    reconciliation_version: 1,
    rule_version: "match.v1",
    evidence: { amount_delta: "12.40", currency: "USD", candidate_count: 1 },
    state: "MISMATCHED",
    outcome: "MISMATCHED",
    supersedes_reconciliation_id: null,
    resolution_id: "res-0007",
  },
  {
    reconciliation_id: "rec-0199",
    batch_id: "batch-201",
    source_a_record_id: null,
    source_b_record_id: "src-B00511",
    raw_record_id: "raw:source-b:source_b.v1:91c4de10",
    reconciliation_version: 1,
    rule_version: "match.v1",
    evidence: { candidate_count: 3, reason: "multiple eligible candidates within tolerance" },
    state: "AMBIGUOUS",
    outcome: "AMBIGUOUS",
    supersedes_reconciliation_id: null,
    resolution_id: null,
  },
  {
    reconciliation_id: "rec-0199-v2",
    batch_id: "batch-201",
    source_a_record_id: "src-A00510",
    source_b_record_id: "src-B00511",
    raw_record_id: "raw:source-b:source_b.v1:91c4de10",
    reconciliation_version: 2,
    rule_version: "match.v1",
    evidence: { candidate_count: 1, operator_decision: "MANUAL_APPROVED" },
    state: "RESOLVED",
    outcome: "MATCHED",
    supersedes_reconciliation_id: "rec-0199",
    resolution_id: "res-0011",
  },
];

export const PLACEHOLDER_DISCREPANCIES: readonly Discrepancy[] = [
  {
    discrepancy_id: "disc-0007",
    reconciliation_id: "rec-0198",
    reason: "amount_delta 12.40 exceeds tolerance 0.01",
    state: "RESOLVED",
  },
  {
    discrepancy_id: "disc-0011",
    reconciliation_id: "rec-0199",
    reason: "3 eligible Source A candidates; ambiguous pairing",
    state: "RESOLVED",
  },
  {
    discrepancy_id: "disc-0014",
    reconciliation_id: "rec-0203",
    reason: "Source A record has no Source B candidate within the matching window",
    state: "OPEN",
  },
  {
    discrepancy_id: "disc-0015",
    reconciliation_id: "rec-0204",
    reason: "Source B record appears twice with identical fingerprint",
    state: "DEFERRED",
  },
  {
    discrepancy_id: "disc-0016",
    reconciliation_id: "rec-0207",
    reason: "unsupported currency code XXX preserved as raw evidence",
    state: "REJECTED",
  },
];

export const PLACEHOLDER_AUDIT_EVENTS: readonly AuditEvent[] = [
  {
    event_id: "evt-0001",
    entity_type: "discrepancy",
    entity_id: "disc-0011",
    event_type: "DISCREPANCY_OPENED",
    actor: "system:matching",
    timestamp: D("2026-09-08T06:03:12Z"),
    sequence: 1,
    stage_version: "match.v1",
    metadata: { reconciliation_id: "rec-0199", candidate_count: 3 },
    previous_state: null,
    new_state: "OPEN",
    batch_id: "batch-201",
    attempt_id: null,
    record_id: null,
    reconciliation_id: "rec-0199",
    causation_event_id: null,
  },
  {
    event_id: "evt-0002",
    entity_type: "discrepancy",
    entity_id: "disc-0011",
    event_type: "RESOLUTION_RECORDED",
    actor: "operator:j.adeyemi",
    timestamp: D("2026-09-08T09:41:55Z"),
    sequence: 2,
    stage_version: "resolution.v1",
    metadata: { resolution_type: "MANUAL_APPROVED", reconciliation_version: 2 },
    previous_state: "OPEN",
    new_state: "RESOLVED",
    batch_id: "batch-201",
    attempt_id: null,
    record_id: null,
    reconciliation_id: "rec-0199-v2",
    causation_event_id: "evt-0001",
  },
];

export const PLACEHOLDER_RESOLUTION_RESULT: ResolutionResult = {
  resolution: {
    resolution_id: "res-0011",
    discrepancy_id: "disc-0011",
    reconciliation_id: "rec-0199-v2",
    resolution_type: "MANUAL_APPROVED",
    actor: "operator:j.adeyemi",
    reason: "Receipt confirms the Source A record pairs with Source B 00511.",
    created_at: D("2026-09-08T09:41:55Z"),
    evidence: { operator_note: "matched on receipt reference", candidate_count: 1 },
    rule_version: "resolution.v1",
  },
  discrepancy: {
    discrepancy_id: "disc-0011",
    reconciliation_id: "rec-0199",
    reason: "3 eligible Source A candidates; ambiguous pairing",
    state: "RESOLVED",
  },
  reconciliation: {
    reconciliation_id: "rec-0199-v2",
    batch_id: "batch-201",
    source_a_record_id: "src-A00510",
    source_b_record_id: "src-B00511",
    raw_record_id: "raw:source-b:source_b.v1:91c4de10",
    reconciliation_version: 2,
    rule_version: "match.v1",
    evidence: { candidate_count: 1, operator_decision: "MANUAL_APPROVED" },
    state: "RESOLVED",
    outcome: "MATCHED",
    supersedes_reconciliation_id: "rec-0199",
    resolution_id: "res-0011",
  },
};
