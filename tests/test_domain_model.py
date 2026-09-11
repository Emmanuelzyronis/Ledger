from datetime import datetime, timezone
from decimal import Decimal
import unittest

from ledger.domain import (
    AuditEvent,
    AuditEventType,
    Batch,
    BatchCounters,
    BatchState,
    CanonicalTransaction,
    Direction,
    Discrepancy,
    DiscrepancyState,
    InvalidTransitionError,
    InvalidValueError,
    MatchCandidate,
    ProcessingAttempt,
    ProcessingAttemptState,
    RawRecord,
    Reconciliation,
    ReconciliationOutcome,
    ReconciliationState,
    Resolution,
    ResolutionType,
    Source,
)


UTC = timezone.utc
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
HASH = "a" * 64


class DomainModelTests(unittest.TestCase):
    def test_canonical_transaction_normalizes_values_and_has_stable_semantic_field_order(self) -> None:
        transaction = CanonicalTransaction(
            canonical_id="can-1",
            source_id="source-a",
            raw_record_id="raw-1",
            source_record_id="A-1",
            occurred_at=datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
            amount="12.5",
            currency="USD",
            direction=Direction.CREDIT,
            normalization_version="canonical_v1",
            canonical_version=1,
            canonical_fingerprint=HASH,
            created_at=NOW,
            transaction_reference="  INV-1 ",
        )
        self.assertEqual(transaction.amount, Decimal("12.5000"))
        self.assertEqual(transaction.transaction_reference, "INV-1")
        self.assertEqual(
            list(transaction.semantic_payload()),
            [
                "occurred_at",
                "amount",
                "currency",
                "direction",
                "transaction_type",
                "account_reference",
                "transaction_reference",
                "description",
                "transaction_status",
            ],
        )

    def test_canonical_transaction_rejects_invalid_values(self) -> None:
        with self.assertRaises(InvalidValueError):
            CanonicalTransaction(
                canonical_id="can-1",
                source_id="source-a",
                raw_record_id="raw-1",
                source_record_id="A-1",
                occurred_at=NOW,
                amount="1.00001",
                currency="USD",
                direction=Direction.CREDIT,
                normalization_version="canonical_v1",
                canonical_version=1,
                canonical_fingerprint=HASH,
                created_at=NOW,
            )

    def test_batch_transitions_and_retry_rules(self) -> None:
        batch = Batch("batch-1", "source-a", "external-1", "source_a.v1", NOW)
        batch = batch.transition_to(BatchState.VALIDATING).transition_to(BatchState.VALIDATED)
        with self.assertRaises(InvalidTransitionError):
            batch.transition_to(BatchState.PROCESSING)
        batch = batch.transition_to(BatchState.PROCESSING, attempt_created=True)
        failed = batch.transition_to(BatchState.FAILED)
        with self.assertRaises(InvalidTransitionError):
            failed.transition_to(BatchState.PROCESSING)
        retried = failed.transition_to(BatchState.PROCESSING, retry=True, attempt_created=True)
        self.assertEqual(retried.state, BatchState.PROCESSING)

    def test_batch_rejection_and_partial_paths_are_guarded(self) -> None:
        rejected = Batch("batch-rejected", "source-a", "external-2", "source_a.v1", NOW)
        rejected = rejected.transition_to(BatchState.VALIDATING).transition_to(BatchState.REJECTED)
        with self.assertRaises(InvalidTransitionError):
            rejected.transition_to(BatchState.VALIDATING)
        counters = BatchCounters(received_count=2, accepted_count=2, processed_count=1, matched_count=1, failed_count=1)
        partial = Batch("batch-partial", "source-a", "external-3", "source_a.v1", NOW, state=BatchState.PROCESSING, counters=counters)
        self.assertEqual(partial.transition_to(BatchState.PARTIAL).state, BatchState.PARTIAL)
        with self.assertRaises(InvalidTransitionError):
            partial.transition_to(BatchState.COMPLETED)

    def test_processing_attempt_lifecycle(self) -> None:
        attempt = ProcessingAttempt("attempt-1", "batch-1", "processing_v1")
        attempt = attempt.transition_to(ProcessingAttemptState.RUNNING, at=NOW)
        attempt = attempt.transition_to(ProcessingAttemptState.COMPLETED, at=NOW)
        self.assertEqual(attempt.state, ProcessingAttemptState.COMPLETED)
        self.assertEqual(attempt.started_at, NOW)
        with self.assertRaises(InvalidTransitionError):
            attempt.transition_to(ProcessingAttemptState.RUNNING, at=NOW)
        with self.assertRaises(InvalidValueError):
            ProcessingAttempt("attempt-2", "batch-1", "processing_v1").transition_to(
                ProcessingAttemptState.RUNNING, at=NOW
            ).transition_to(ProcessingAttemptState.COMPLETED, at=datetime(2026, 9, 7, 11, 0, tzinfo=UTC))

    def test_reconciliation_covers_all_outcomes_and_resolution(self) -> None:
        outcomes = [
            ReconciliationOutcome.MATCHED,
            ReconciliationOutcome.MISMATCHED,
            ReconciliationOutcome.UNMATCHED_A,
            ReconciliationOutcome.UNMATCHED_B,
            ReconciliationOutcome.AMBIGUOUS,
            ReconciliationOutcome.DUPLICATE,
            ReconciliationOutcome.INVALID,
        ]
        for outcome in outcomes:
            reconciliation = Reconciliation("rec-" + outcome.value.lower(), "batch-1", "A-1", "B-1", 1, "standard_v1", {})
            result = reconciliation.transition_to(ReconciliationState.EVALUATING).transition_to(ReconciliationState(outcome.value))
            self.assertEqual(result.outcome, outcome)

        reconciliation = Reconciliation("rec-mismatch", "batch-1", "A-1", "B-1", 1, "standard_v1", {})
        mismatch = reconciliation.transition_to(ReconciliationState.EVALUATING).transition_to(ReconciliationState.MISMATCHED)
        with self.assertRaises(InvalidValueError):
            mismatch.transition_to(ReconciliationState.RESOLVED)
        resolved = mismatch.transition_to(ReconciliationState.RESOLVED, resolution_id="resolution-1")
        self.assertEqual(resolved.state, ReconciliationState.RESOLVED)
        self.assertEqual(resolved.outcome, ReconciliationOutcome.MISMATCHED)

    def test_reconciliation_rejects_invalid_state_and_target(self) -> None:
        with self.assertRaises(InvalidValueError):
            Reconciliation("rec-1", "batch-1", "A-1", "B-1", 1, "standard_v1", {}, state="CREATED")
        reconciliation = Reconciliation("rec-1", "batch-1", "A-1", "B-1", 1, "standard_v1", {})
        with self.assertRaises(InvalidValueError):
            reconciliation.transition_to("EVALUATING")

    def test_match_candidate_freezes_rule_ids_and_rejects_illegal_shape(self) -> None:
        candidate = MatchCandidate("candidate-1", "can-a", "can-b", ["M-001"], {"date_delta_days": 0})
        self.assertEqual(candidate.eligible_rule_ids, ("M-001",))
        with self.assertRaises(TypeError):
            candidate.evidence["date_delta_days"] = 1

    def test_canonical_correction_links_to_prior_version(self) -> None:
        corrected = CanonicalTransaction(
            canonical_id="can-2",
            source_id="source-a",
            raw_record_id="raw-2",
            source_record_id="A-1",
            occurred_at=NOW,
            amount=Decimal("12.5000"),
            currency="USD",
            direction=Direction.CREDIT,
            normalization_version="canonical_v1",
            canonical_version=2,
            canonical_fingerprint=HASH,
            created_at=NOW,
            supersedes_canonical_id="can-1",
        )
        self.assertEqual(corrected.canonical_version, 2)
        self.assertEqual(corrected.supersedes_canonical_id, "can-1")

    def test_processing_attempt_terminal_failure_paths_are_explicit(self) -> None:
        for terminal in (ProcessingAttemptState.FAILED, ProcessingAttemptState.TIMED_OUT, ProcessingAttemptState.CANCELLED):
            attempt = ProcessingAttempt("attempt-" + terminal.value.lower(), "batch-1", "processing_v1")
            ended = attempt.transition_to(ProcessingAttemptState.RUNNING, at=NOW).transition_to(terminal, at=NOW, error="stopped")
            self.assertEqual(ended.state, terminal)
            with self.assertRaises(InvalidTransitionError):
                ended.transition_to(ProcessingAttemptState.RUNNING, at=NOW)

    def test_discrepancy_and_resolution_authority(self) -> None:
        discrepancy = Discrepancy("disc-1", "rec-1", "amount differs")
        deferred = discrepancy.transition_to(DiscrepancyState.DEFERRED)
        with self.assertRaises(InvalidTransitionError):
            deferred.transition_to(DiscrepancyState.OPEN)
        resolution = Resolution(
            "resolution-1",
            "disc-1",
            "rec-1",
            ResolutionType.MANUAL_APPROVED,
            "reconciliation_operator",
            "verified against source evidence",
            NOW,
        )
        self.assertEqual(resolution.actor, "reconciliation_operator")
        with self.assertRaises(InvalidValueError):
            Resolution("resolution-2", "disc-1", "rec-1", ResolutionType.MANUAL_APPROVED, "other", "reason", NOW)

        resolved = Discrepancy("disc-2", "rec-2", "amount differs").transition_to(DiscrepancyState.RESOLVED)
        rejected = Discrepancy("disc-3", "rec-3", "invalid source").transition_to(DiscrepancyState.REJECTED)
        self.assertEqual(resolved.state, DiscrepancyState.RESOLVED)
        self.assertEqual(rejected.state, DiscrepancyState.REJECTED)
        with self.assertRaises(InvalidTransitionError):
            resolved.transition_to(DiscrepancyState.OPEN)

    def test_raw_record_and_audit_event_are_immutable_domain_values(self) -> None:
        raw = RawRecord("raw-1", "source-a", "batch-1", "A-1", "source_a.v1", {"record_id": "A-1", "nested": {"value": 1}}, HASH, NOW)
        self.assertEqual(raw.payload, {"record_id": "A-1", "nested": {"value": 1}})
        with self.assertRaises(TypeError):
            raw.payload["record_id"] = "changed"
        with self.assertRaises(TypeError):
            raw.payload["nested"]["value"] = 2
        event = AuditEvent("audit-1", "batch", "batch-1", AuditEventType.BATCH_RECEIVED, "system", NOW, 1, "foundation_v1", batch_id="batch-1")
        self.assertEqual(event.sequence, 1)

    def test_batch_counters_enforce_architectural_equations(self) -> None:
        counters = BatchCounters(received_count=3, accepted_count=3, processed_count=3, matched_count=1, unmatched_count=1, invalid_count=1)
        self.assertEqual(counters.processed_count, 3)
        with self.assertRaises(InvalidValueError):
            BatchCounters(received_count=1, accepted_count=1, processed_count=0, matched_count=1)

    def test_batch_terminal_preconditions_are_explicit(self) -> None:
        counters = BatchCounters(received_count=1, accepted_count=1, processed_count=0, failed_count=1)
        batch = Batch("batch-1", "source-a", "external-1", "source_a.v1", NOW, state=BatchState.PROCESSING, counters=counters)
        with self.assertRaises(InvalidTransitionError):
            batch.transition_to(BatchState.COMPLETED)
        partial = batch.transition_to(BatchState.PARTIAL)
        self.assertEqual(partial.state, BatchState.PARTIAL)

    def test_source_schema_versions_are_unique(self) -> None:
        Source("source-a", "Bank A", ("source_a.v1",))
        with self.assertRaises(InvalidValueError):
            Source("source-a", "Bank A", ("source_a.v1", "source_a.v1"))


if __name__ == "__main__":
    unittest.main()
