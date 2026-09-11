"""Layer 14 failure-verification regression suite.

Every injected fault uses a real service boundary and, where possible, fails
after an earlier authoritative write has already occurred. The test then
proves the transaction rolled back completely and that a retry produces the
same logical result without duplicating authoritative records.
"""

from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
import unittest

from ledger.candidates import CandidateGenerationService
from ledger.domain import (
    AuditEvent,
    AuditEventType,
    Batch,
    BatchState,
    Discrepancy,
    DiscrepancyState,
    ProcessingAttempt,
    ProcessingAttemptState,
    Reconciliation,
    ReconciliationOutcome,
    ReconciliationState,
    ResolutionType,
)
from ledger.domain.errors import InvalidTransitionError
from ledger.identity import IdentityService
from ledger.ingestion import RawIngestion
from ledger.matching import MatchingService
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.reconciliation import ReconciliationService
from ledger.resolution import ResolutionService
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


class FailureVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = LedgerDatabase()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "Source A", ["source_a.v1"])
        self.ingestion.register_source("b", "Source B", ["source_b.v1"])
        self.validation = ValidationService(self.db)
        self.normalization = NormalizationService(self.db)
        self.sequence = 0

    def tearDown(self) -> None:
        self.db.close()

    def count(self, table: str) -> int:
        return self.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def _payload(self, source: str, record_id: str, *, amount: str, date: str, reference: str | None, direction: str) -> dict[str, str]:
        if source == "a":
            return {
                "record_id": record_id,
                "occurred_at": date,
                "amount": amount,
                "currency": "USD",
                "direction": direction,
            }
        payload = {
            "id": record_id,
            "posted": date,
            "value": amount,
            "ccy": "USD",
            "side": direction,
        }
        if reference:
            payload["reference"] = reference
        return payload

    def ingest_raw(self, source: str, record_id: str, *, amount: str = "10", date: str = "2026-09-08", reference: str | None = None, direction: str = "CREDIT"):
        self.sequence += 1
        schema = "source_a.v1" if source == "a" else "source_b.v1"
        batch = self.ingestion.create_batch(
            source, f"fv-external-{self.sequence}", schema,
            batch_id=f"fv-batch-{self.sequence}", received_at=NOW,
        )
        raw = self.ingestion.ingest(
            batch.batch_id,
            self._payload(source, record_id, amount=amount, date=date, reference=reference, direction=direction),
            accepted_at=NOW,
        )
        return batch, raw

    def canonical(self, source: str, record_id: str, *, amount: str = "10", date: str = "2026-09-08", reference: str | None = None, direction: str = "CREDIT"):
        batch, raw = self.ingest_raw(source, record_id, amount=amount, date=date, reference=reference, direction=direction)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        transaction = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        return transaction, batch

    def test_database_interruption_rolls_back_ingestion_and_retry_is_idempotent(self):
        batch = self.ingestion.create_batch("a", "fv-db", "source_a.v1", batch_id="fv-db-batch", received_at=NOW)
        payload = {"record_id": "A-1", "occurred_at": "2026-09-08", "amount": "10", "currency": "USD", "direction": "CREDIT"}
        original = self.db.raw_records.save
        self.db.raw_records.save = lambda record: (_ for _ in ()).throw(sqlite3.OperationalError("injected database interruption"))
        try:
            with self.assertRaises(sqlite3.OperationalError):
                self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        finally:
            self.db.raw_records.save = original
        self.assertEqual(self.count("raw_records"), 0)
        self.assertEqual(self.count("ingestion_submissions"), 0)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.received_count, 0)
        first = self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        retry = self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        self.assertEqual(first.raw_record_id, retry.raw_record_id)
        self.assertTrue(retry.duplicate_submission)
        self.assertEqual(self.count("raw_records"), 1)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.received_count, 1)

    def test_interrupted_batch_retry_completes_without_duplicates_or_loss(self):
        batch = self.ingestion.create_batch("a", "fv-partial", "source_a.v1", batch_id="fv-partial-batch", received_at=NOW)
        first_payload = {"record_id": "A-1", "occurred_at": "2026-09-08", "amount": "10", "currency": "USD", "direction": "CREDIT"}
        second_payload = {"record_id": "A-2", "occurred_at": "2026-09-08", "amount": "11", "currency": "USD", "direction": "CREDIT"}
        first = self.ingestion.ingest(batch.batch_id, first_payload, accepted_at=NOW)
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("injected audit interruption"))
        try:
            with self.assertRaises(RuntimeError):
                self.ingestion.ingest(batch.batch_id, second_payload, accepted_at=NOW)
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.count("raw_records"), 1)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.received_count, 1)
        self.assertEqual(dict(self.db.raw_records.get(first.raw_record_id).payload), first_payload)
        recovered = self.ingestion.ingest(batch.batch_id, second_payload, accepted_at=NOW)
        duplicate = self.ingestion.ingest(batch.batch_id, second_payload, accepted_at=NOW)
        self.assertEqual(recovered.status, "ACCEPTED")
        self.assertEqual(recovered.raw_record_id, duplicate.raw_record_id)
        self.assertTrue(duplicate.duplicate_submission)
        self.assertEqual(self.count("raw_records"), 2)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.received_count, 2)

    def test_validation_batch_failure_remains_retryable_without_duplicate_results(self):
        batch, _ = self.ingest_raw("a", "A-1")
        original = self.db.validation_results.save
        self.db.validation_results.save = lambda result: (_ for _ in ()).throw(RuntimeError("injected validation persistence failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.validation.validate_batch(batch.batch_id)
        finally:
            self.db.validation_results.save = original
        current = self.db.batches.get(batch.batch_id)
        self.assertEqual(current.state, BatchState.VALIDATING)
        self.assertEqual(current.counters.processed_count, 0)
        self.assertEqual(self.count("validation_results"), 0)
        results = self.validation.validate_batch(batch.batch_id)
        self.assertEqual(len(results), 1)
        self.assertEqual(self.db.batches.get(batch.batch_id).state, BatchState.VALIDATED)
        repeated = self.validation.validate_batch(batch.batch_id)
        self.assertEqual([result.validation_id for result in results], [result.validation_id for result in repeated])
        self.assertEqual(self.count("validation_results"), 1)
        self.assertEqual(self.count("audit_events"), 5)

    def test_normalization_audit_failure_rolls_back_and_retry_is_idempotent(self):
        batch, raw = self.ingest_raw("a", "A-1")
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("injected normalization audit failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.count("canonical_transactions"), 0)
        self.assertEqual(self.count("audit_events"), 3)
        first = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        second = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        self.assertEqual(first, second)
        self.assertEqual(self.count("canonical_transactions"), 1)
        self.assertEqual(self.count("audit_events"), 4)

    def test_identity_rejects_corrupt_lineage_without_state_change(self):
        canonical, _ = self.canonical("a", "A-1")
        before = self.count("canonical_transactions")
        corrupted_fingerprint = replace(canonical, canonical_fingerprint="f" * 64)
        corrupted_id = replace(canonical, canonical_id="can:corrupt", canonical_fingerprint="f" * 64)
        identity = IdentityService(self.db)
        with self.assertRaises(ValueError):
            identity.identify(corrupted_fingerprint)
        with self.assertRaises(ValueError):
            identity.identify(corrupted_id)
        self.assertEqual(self.count("canonical_transactions"), before)
        self.assertEqual(self.db.canonical_transactions.get(canonical.canonical_id), canonical)

    def test_candidate_persistence_failure_rolls_back_batch_and_retry_is_idempotent(self):
        self.canonical("a", "A-1", amount="10")
        self.canonical("b", "B-1", amount="10")
        self.canonical("a", "A-2", amount="11")
        self.canonical("b", "B-2", amount="11")
        generator = CandidateGenerationService(self.db)
        audit_before = self.count("audit_events")
        original = self.db.match_candidates.save
        calls: list[object] = []

        def fail_second(candidate: object):
            calls.append(candidate)
            if len(calls) == 2:
                raise RuntimeError("injected candidate persistence failure")
            return original(candidate)

        self.db.match_candidates.save = fail_second
        try:
            with self.assertRaises(RuntimeError):
                generator.generate_all()
        finally:
            self.db.match_candidates.save = original
        self.assertEqual(self.count("match_candidates"), 0)
        self.assertEqual(self.count("audit_events"), audit_before)
        first = generator.generate_all()
        repeated = generator.generate_all()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(repeated), 2)
        self.assertEqual(self.count("match_candidates"), 2)
        self.assertEqual(self.count("reconciliations"), 0)

    def test_reconciliation_discrepancy_failure_rolls_back_decision_and_retry_is_idempotent(self):
        can_a, batch_a = self.canonical("a", "A-1")
        can_b, _ = self.canonical("b", "B-1")
        service = ReconciliationService(self.db)
        audit_before = self.count("audit_events")
        original = self.db.discrepancies.save
        self.db.discrepancies.save = lambda discrepancy: (_ for _ in ()).throw(RuntimeError("injected discrepancy persistence failure"))
        try:
            with self.assertRaises(RuntimeError):
                service.persist_decision(
                    batch_id=batch_a.batch_id,
                    source_a_record_id=can_a.canonical_id,
                    source_b_record_id=can_b.canonical_id,
                    outcome=ReconciliationOutcome.MISMATCHED,
                    evidence={},
                    evaluated_at=NOW,
                )
        finally:
            self.db.discrepancies.save = original
        self.assertEqual(self.count("reconciliations"), 0)
        self.assertEqual(self.count("discrepancies"), 0)
        self.assertEqual(self.count("audit_events"), audit_before)
        first = service.persist_decision(
            batch_id=batch_a.batch_id,
            source_a_record_id=can_a.canonical_id,
            source_b_record_id=can_b.canonical_id,
            outcome=ReconciliationOutcome.MISMATCHED,
            evidence={},
            evaluated_at=NOW,
        )
        repeated = service.persist_decision(
            batch_id=batch_a.batch_id,
            source_a_record_id=can_a.canonical_id,
            source_b_record_id=can_b.canonical_id,
            outcome=ReconciliationOutcome.MISMATCHED,
            evidence={},
            evaluated_at=NOW,
        )
        self.assertEqual(first, repeated)
        self.assertEqual(self.count("reconciliations"), 1)
        self.assertEqual(self.count("discrepancies"), 1)

    def test_reconciliation_audit_failure_after_first_event_rolls_back_all_state(self):
        can_a, batch_a = self.canonical("a", "A-1")
        can_b, _ = self.canonical("b", "B-1")
        service = ReconciliationService(self.db)
        audit_before = self.count("audit_events")
        original = self.db.audit_events.append
        calls: list[object] = []

        def fail_second_append(event: object):
            calls.append(event)
            if len(calls) == 2:
                raise RuntimeError("injected audit failure after first event")
            return original(event)

        self.db.audit_events.append = fail_second_append
        try:
            with self.assertRaises(RuntimeError):
                service.persist_decision(
                    batch_id=batch_a.batch_id,
                    source_a_record_id=can_a.canonical_id,
                    source_b_record_id=can_b.canonical_id,
                    outcome=ReconciliationOutcome.MISMATCHED,
                    evidence={},
                    evaluated_at=NOW,
                )
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.count("reconciliations"), 0)
        self.assertEqual(self.count("discrepancies"), 0)
        self.assertEqual(self.count("audit_events"), audit_before)
        service.persist_decision(
            batch_id=batch_a.batch_id,
            source_a_record_id=can_a.canonical_id,
            source_b_record_id=can_b.canonical_id,
            outcome=ReconciliationOutcome.MISMATCHED,
            evidence={},
            evaluated_at=NOW,
        )
        self.assertEqual(self.count("reconciliations"), 1)
        self.assertEqual(self.count("discrepancies"), 1)
        self.assertEqual(self.count("audit_events"), audit_before + 2)

    def test_matching_partial_failure_recovers_without_duplicate_decisions(self):
        for amount in ("10", "11", "12"):
            self.canonical("a", f"A-{amount}", amount=amount)
            self.canonical("b", f"B-{amount}", amount=amount)
        candidates = CandidateGenerationService(self.db).generate_all()
        self.assertEqual(len(candidates), 3)
        matching = MatchingService(self.db)
        original = matching.reconciliation.persist_decision
        calls: list[tuple[object, ...]] = []

        def fail_third(*args: object, **kwargs: object):
            calls.append(args)
            if len(calls) == 3:
                raise RuntimeError("injected matching persistence failure")
            return original(*args, **kwargs)

        matching.reconciliation.persist_decision = fail_third  # type: ignore[method-assign]
        try:
            with self.assertRaises(RuntimeError):
                matching.evaluate(evaluated_at=NOW)
        finally:
            matching.reconciliation.persist_decision = original  # type: ignore[method-assign]
        self.assertEqual(self.count("reconciliations"), 2)
        recovered = matching.evaluate(evaluated_at=NOW)
        repeated = matching.evaluate(evaluated_at=NOW)
        self.assertEqual(len(recovered), 3)
        self.assertEqual(len(repeated), 3)
        self.assertEqual(self.count("reconciliations"), 3)
        self.assertEqual(self.count("discrepancies"), 0)
        self.assertTrue(all(decision.outcome is ReconciliationOutcome.MATCHED for decision in recovered))

    def test_late_reprocessing_preserves_prior_decisions_without_duplicates(self):
        for amount in ("10", "11"):
            self.canonical("a", f"A-{amount}", amount=amount)
            self.canonical("b", f"B-{amount}", amount=amount)
        CandidateGenerationService(self.db).generate_all()
        first_decisions = MatchingService(self.db).evaluate(evaluated_at=NOW)
        first_ids = [decision.reconciliation.reconciliation_id for decision in first_decisions]
        first_rows = [self.db.reconciliations.get(reconciliation_id) for reconciliation_id in first_ids]
        self.assertEqual(len(first_rows), 2)
        self.canonical("a", "A-12", amount="12")
        self.canonical("b", "B-12", amount="12")
        CandidateGenerationService(self.db).generate_all()
        second_decisions = MatchingService(self.db).evaluate(evaluated_at=NOW)
        third_decisions = MatchingService(self.db).evaluate(evaluated_at=NOW)
        self.assertEqual(len(second_decisions), 3)
        self.assertEqual(len(third_decisions), 3)
        self.assertEqual(self.count("reconciliations"), 3)
        self.assertEqual(self.count("raw_records"), 6)
        self.assertEqual([self.db.reconciliations.get(reconciliation_id) for reconciliation_id in first_ids], first_rows)
        self.assertEqual(self.count("discrepancies"), 0)

    def test_resolution_audit_failure_after_partial_writes_rolls_back_all_state(self):
        can_a, batch_a = self.canonical("a", "A-1")
        can_b, _ = self.canonical("b", "B-1")
        reconciliation = Reconciliation(
            "fv-rec-resolution", batch_a.batch_id, can_a.canonical_id, can_b.canonical_id,
            1, "standard_v1", {"injected": True},
            ReconciliationState.MISMATCHED, ReconciliationOutcome.MISMATCHED,
        )
        self.db.reconciliations.save(reconciliation)
        discrepancy = Discrepancy("fv-disc-resolution", reconciliation.reconciliation_id, "injected mismatch")
        self.db.discrepancies.save(discrepancy)
        service = ResolutionService(self.db)
        audit_before = self.count("audit_events")
        original = self.db.audit_events.append
        calls: list[object] = []

        def fail_third_append(event: object):
            calls.append(event)
            if len(calls) == 3:
                raise RuntimeError("injected audit failure after partial resolution writes")
            return original(event)

        self.db.audit_events.append = fail_third_append
        try:
            with self.assertRaises(RuntimeError):
                service.resolve(
                    discrepancy.discrepancy_id,
                    ResolutionType.MANUAL_APPROVED,
                    actor="reconciliation_operator",
                    reason="verified",
                    created_at=NOW,
                )
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.db.discrepancies.get(discrepancy.discrepancy_id).state, DiscrepancyState.OPEN)
        self.assertEqual(self.count("reconciliations"), 1)
        self.assertEqual(self.count("resolutions"), 0)
        self.assertEqual(self.count("audit_events"), audit_before)
        result = service.resolve(
            discrepancy.discrepancy_id,
            ResolutionType.MANUAL_APPROVED,
            actor="reconciliation_operator",
            reason="verified",
            created_at=NOW,
        )
        repeated = service.resolve(
            discrepancy.discrepancy_id,
            ResolutionType.MANUAL_APPROVED,
            actor="reconciliation_operator",
            reason="verified",
            created_at=NOW,
        )
        self.assertEqual(result, repeated)
        self.assertEqual(result.discrepancy.state, DiscrepancyState.RESOLVED)
        self.assertEqual(self.count("reconciliations"), 2)
        self.assertEqual(self.count("resolutions"), 1)
        self.assertEqual(self.count("audit_events"), audit_before + 3)

    def test_processing_attempt_failure_state_and_retry_remain_valid(self):
        batch = Batch("fv-attempt-batch", "a", "fv-attempt-external", "source_a.v1", NOW)
        self.db.batches.save(batch)
        first = ProcessingAttempt("fv-attempt-1", batch.batch_id, "processing_v1")
        self.db.processing_attempts.save(first)
        run_event = AuditEvent(
            "fv-attempt-run-1", "processing_attempt", first.attempt_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state="CREATED", new_state="RUNNING",
            batch_id=batch.batch_id, attempt_id=first.attempt_id,
        )
        running = self.db.processing_attempts.transition_with_audit(first, ProcessingAttemptState.RUNNING, run_event, at=NOW)
        self.assertEqual(running.state, ProcessingAttemptState.RUNNING)
        fail_event = AuditEvent(
            "fv-attempt-fail-1", "processing_attempt", first.attempt_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state="RUNNING", new_state="FAILED",
            batch_id=batch.batch_id, attempt_id=first.attempt_id,
        )
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("injected attempt audit failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.db.processing_attempts.transition_with_audit(running, ProcessingAttemptState.FAILED, fail_event, at=NOW, error="injected")
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.db.processing_attempts.get(first.attempt_id).state, ProcessingAttemptState.RUNNING)
        self.assertIsNone(self.db.audit_events.get(fail_event.event_id))
        failed = self.db.processing_attempts.transition_with_audit(running, ProcessingAttemptState.FAILED, fail_event, at=NOW, error="injected")
        self.assertEqual(failed.state, ProcessingAttemptState.FAILED)
        retry = ProcessingAttempt("fv-attempt-2", batch.batch_id, "processing_v1", retry_of_attempt_id=first.attempt_id)
        self.db.processing_attempts.save(retry)
        run_retry_event = AuditEvent(
            "fv-attempt-run-2", "processing_attempt", retry.attempt_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state="CREATED", new_state="RUNNING",
            batch_id=batch.batch_id, attempt_id=retry.attempt_id,
        )
        running_retry = self.db.processing_attempts.transition_with_audit(retry, ProcessingAttemptState.RUNNING, run_retry_event, at=NOW)
        complete_retry_event = AuditEvent(
            "fv-attempt-complete-2", "processing_attempt", retry.attempt_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state="RUNNING", new_state="COMPLETED",
            batch_id=batch.batch_id, attempt_id=retry.attempt_id,
        )
        completed = self.db.processing_attempts.transition_with_audit(running_retry, ProcessingAttemptState.COMPLETED, complete_retry_event, at=NOW)
        self.assertEqual(completed.state, ProcessingAttemptState.COMPLETED)
        self.assertEqual(self.db.processing_attempts.get(first.attempt_id).state, ProcessingAttemptState.FAILED)
        self.assertEqual(self.db.processing_attempts.get(retry.attempt_id).retry_of_attempt_id, first.attempt_id)

    def test_invalid_and_corrupt_input_is_explicit_and_never_processed(self):
        batch = self.ingestion.create_batch("a", "fv-invalid", "source_a.v1", batch_id="fv-invalid-batch", received_at=NOW)
        rejected = self.ingestion.ingest(batch.batch_id, ["not", "an", "object"], accepted_at=NOW)
        invalid = self.ingestion.ingest(
            batch.batch_id,
            {"occurred_at": "not-a-date", "amount": "10", "currency": "USD", "direction": "CREDIT"},
            accepted_at=NOW,
        )
        self.assertEqual(rejected.status, "REJECTED")
        self.assertIsNone(rejected.raw_record_id)
        self.assertEqual(invalid.status, "INVALID")
        raw_id = invalid.raw_record_id
        self.assertIsNotNone(raw_id)
        preserved = dict(self.db.raw_records.get(raw_id).payload)
        self.validation.validate_record(raw_id, validated_at=NOW)
        self.assertIsNone(self.normalization.normalize_record(raw_id))
        self.assertEqual(dict(self.db.raw_records.get(raw_id).payload), preserved)
        self.assertEqual(self.count("canonical_transactions"), 0)
        self.assertEqual(self.count("match_candidates"), 0)
        self.assertEqual(self.count("reconciliations"), 0)

    def test_terminal_states_reject_illegal_transitions_without_mutation_or_audit(self):
        batch = Batch("fv-terminal-batch", "a", "fv-external", "source_a.v1", NOW, state=BatchState.REJECTED)
        self.db.batches.save(batch)
        event = AuditEvent(
            "fv-terminal-event", "batch", batch.batch_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state=batch.state.value, new_state="VALIDATING", batch_id=batch.batch_id,
        )
        with self.assertRaises(InvalidTransitionError):
            self.db.batches.transition_with_audit(batch, BatchState.VALIDATING, event)
        self.assertEqual(self.db.batches.get(batch.batch_id).state, BatchState.REJECTED)
        attempt = ProcessingAttempt("fv-terminal-attempt", batch.batch_id, "processing_v1", state=ProcessingAttemptState.FAILED)
        self.db.processing_attempts.save(attempt)
        attempt_event = AuditEvent(
            "fv-terminal-attempt-event", "processing_attempt", attempt.attempt_id,
            AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
            previous_state=attempt.state.value, new_state="RUNNING",
            batch_id=batch.batch_id, attempt_id=attempt.attempt_id,
        )
        with self.assertRaises(InvalidTransitionError):
            self.db.processing_attempts.transition_with_audit(attempt, ProcessingAttemptState.RUNNING, attempt_event, at=NOW)
        self.assertEqual(self.db.processing_attempts.get(attempt.attempt_id).state, ProcessingAttemptState.FAILED)
        self.assertEqual(self.count("audit_events"), 0)


if __name__ == "__main__":
    unittest.main()
