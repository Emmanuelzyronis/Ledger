from datetime import datetime, timezone, timedelta
from decimal import Decimal
import unittest
import sqlite3

from ledger.domain import (
    AuditEvent,
    AuditEventType,
    Batch,
    BatchState,
    CanonicalTransaction,
    Direction,
    Discrepancy,
    DiscrepancyState,
    ProcessingAttempt,
    ProcessingAttemptState,
    RawRecord,
    Reconciliation,
    ReconciliationOutcome,
    Resolution,
    ResolutionType,
    ReconciliationState,
    Source,
)
from ledger.persistence import LedgerDatabase, UniqueConstraintError


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = LedgerDatabase()
        self.database.sources.save(Source("source-a", "Source A", ("source_a.v1",)))
        self.database.sources.save(Source("source-b", "Source B", ("source_b.v1",)))
        self.batch = Batch("batch-1", "source-a", "external-1", "source_a.v1", NOW)
        self.database.batches.save(self.batch)

    def tearDown(self) -> None:
        self.database.close()

    def _raw(self, raw_id: str = "raw-1", fingerprint: str = HASH_A) -> RawRecord:
        return RawRecord(raw_id, "source-a", "batch-1", "A-1", "source_a.v1", {"record_id": "A-1", "amount": "10.00"}, fingerprint, NOW)

    def _canonical(self, canonical_id: str = "can-1", raw_id: str = "raw-1") -> CanonicalTransaction:
        return CanonicalTransaction(canonical_id, "source-a", raw_id, "A-1", NOW, Decimal("10.0000"), "USD", Direction.CREDIT,
                                    "canonical_v1", 1, HASH_A, NOW)

    def test_round_trip_all_core_records_and_foreign_keys(self) -> None:
        raw = self._raw()
        self.database.raw_records.save(raw)
        canonical = self._canonical()
        self.database.canonical_transactions.save(canonical)
        reconciliation = Reconciliation("rec-1", "batch-1", "can-1", None, 1, "standard_v1", {})
        self.database.reconciliations.save(reconciliation)
        self.assertEqual(self.database.raw_records.get("raw-1"), raw)
        self.assertEqual(self.database.canonical_transactions.get("can-1"), canonical)
        self.assertEqual(self.database.reconciliations.get("rec-1"), reconciliation)

    def test_raw_replay_reuses_identity_and_adds_batch_association(self) -> None:
        self.database.raw_records.save(self._raw())
        second_batch = Batch("batch-2", "source-a", "external-2", "source_a.v1", NOW)
        self.database.batches.save(second_batch)
        replay = RawRecord("different-id", "source-a", "batch-2", "A-1", "source_a.v1", {"amount": "10.00", "record_id": "A-1"}, HASH_A, NOW)
        reused = self.database.raw_records.save(replay)
        self.assertEqual(reused.raw_record_id, "raw-1")
        associations = self.database.connection.execute("SELECT COUNT(*) FROM raw_record_batches WHERE raw_record_id = 'raw-1'").fetchone()[0]
        self.assertEqual(associations, 2)

    def test_historical_records_are_insert_only(self) -> None:
        self.database.raw_records.save(self._raw())
        with self.assertRaises(UniqueConstraintError):
            self.database.raw_records.save(self._raw(fingerprint=HASH_B))
        self.database.canonical_transactions.save(self._canonical())
        with self.assertRaises(UniqueConstraintError):
            self.database.canonical_transactions.save(self._canonical(canonical_id="can-2"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("UPDATE raw_records SET invalid_reason = 'changed' WHERE raw_record_id = 'raw-1'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM canonical_transactions WHERE canonical_id = 'can-1'")

    def test_versioned_correction_is_persisted_without_overwrite(self) -> None:
        self.database.raw_records.save(self._raw())
        corrected_raw = RawRecord("raw-2", "source-a", "batch-1", "A-1", "source_a.v1", {"record_id": "A-1", "amount": "11.00"}, HASH_B, NOW, supersedes_raw_record_id="raw-1")
        self.database.raw_records.save(corrected_raw)
        self.database.canonical_transactions.save(self._canonical())
        corrected = CanonicalTransaction("can-2", "source-a", "raw-2", "A-1", NOW, Decimal("11.0000"), "USD", Direction.CREDIT,
                                         "canonical_v1", 2, HASH_B, NOW, supersedes_canonical_id="can-1")
        self.database.canonical_transactions.save(corrected)
        self.assertIsNotNone(self.database.raw_records.get("raw-1"))
        self.assertEqual(self.database.canonical_transactions.get("can-2"), corrected)

    def test_audit_append_is_idempotent_and_sequences_are_unique(self) -> None:
        event = AuditEvent("event-1", "batch", "batch-1", AuditEventType.BATCH_RECEIVED, "system", NOW, 1, "foundation_v1", batch_id="batch-1")
        self.assertEqual(self.database.audit_events.append(event), event)
        self.assertEqual(self.database.audit_events.append(event), event)
        self.assertEqual(
            self.database.audit_events.append(
                AuditEvent("event-1", "batch", "batch-1", AuditEventType.BATCH_RECEIVED, "different-actor", NOW + timedelta(seconds=5), 1, "foundation_v1", batch_id="batch-1")
            ),
            event,
        )
        second = self.database.audit_events.append(
            AuditEvent("event-2", "batch", "batch-1", AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "foundation_v1", batch_id="batch-1")
        )
        self.assertEqual(second.sequence, 2)
        self.assertEqual([item.sequence for item in self.database.audit_events.list_for_entity("batch", "batch-1")], [1, 2])

    def test_reconciliation_transition_creates_superseding_version_and_audit_atomically(self) -> None:
        self.database.raw_records.save(self._raw())
        self.database.canonical_transactions.save(self._canonical())
        self.database.raw_records.save(self._raw("raw-2", HASH_B))
        self.database.canonical_transactions.save(self._canonical("can-2", "raw-2"))
        current = Reconciliation("rec-1", "batch-1", "can-1", None, 1, "standard_v1", {})
        self.database.reconciliations.save(current)
        next_version = Reconciliation("rec-2", "batch-1", "can-1", None, 2, "standard_v1", {},
                                      ReconciliationState.EVALUATING, None, "rec-1")
        event = AuditEvent("rec-event-1", "reconciliation", "rec-2", AuditEventType.RECONCILIATION_CREATED,
                           "system", NOW, 99, "reconciliation_v1", reconciliation_id="rec-2")
        persisted = self.database.reconciliations.transition_with_audit(current, ReconciliationState.EVALUATING, next_version, event)
        self.assertEqual(persisted, next_version)
        self.assertIsNotNone(self.database.reconciliations.get("rec-1"))
        self.assertEqual(self.database.reconciliations.get("rec-2"), next_version)
        self.assertEqual(self.database.audit_events.get("rec-event-1").sequence, 1)

    def test_reconciliation_transition_rolls_back_superseding_version_on_audit_failure(self) -> None:
        self.database.raw_records.save(self._raw())
        self.database.canonical_transactions.save(self._canonical())
        current = Reconciliation("rec-1", "batch-1", "can-1", None, 1, "standard_v1", {})
        self.database.reconciliations.save(current)
        next_version = Reconciliation("rec-2", "batch-1", "can-1", None, 2, "standard_v1", {},
                                      ReconciliationState.EVALUATING, None, "rec-1")
        event = AuditEvent("rec-event-1", "reconciliation", "rec-2", AuditEventType.RECONCILIATION_CREATED,
                           "system", NOW, 1, "reconciliation_v1", reconciliation_id="rec-2")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.database.transaction():
                self.database.reconciliations.transition_with_audit(current, ReconciliationState.EVALUATING, next_version, event)
                self.database.connection.execute("INSERT INTO audit_events(event_id, entity_type, entity_id, event_type, actor, timestamp, sequence, stage_version, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                                 ("rec-event-1", "reconciliation", "rec-2", "BATCH_RECEIVED", "system", NOW.isoformat(), 1, "x", "{}"))
        self.assertIsNone(self.database.reconciliations.get("rec-2"))

    def test_resolution_persists_all_authoritative_changes_atomically(self) -> None:
        self.database.raw_records.save(self._raw())
        self.database.canonical_transactions.save(self._canonical())
        self.database.raw_records.save(self._raw("raw-2", HASH_B))
        self.database.canonical_transactions.save(self._canonical("can-2", "raw-2"))
        current = Reconciliation("rec-1", "batch-1", "can-1", "can-2", 1, "standard_v1", {},
                                 ReconciliationState.MISMATCHED, ReconciliationOutcome.MISMATCHED)
        self.database.reconciliations.save(current)
        discrepancy = Discrepancy("disc-1", "rec-1", "amount differs")
        self.database.discrepancies.save(discrepancy)
        resolution = Resolution("res-1", "disc-1", "rec-1", ResolutionType.MANUAL_APPROVED,
                                "reconciliation_operator", "approved correction", NOW)
        next_reconciliation = Reconciliation("rec-2", "batch-1", "can-1", "can-2", 2, "standard_v1", {},
                                             ReconciliationState.RESOLVED, ReconciliationOutcome.MISMATCHED, "rec-1", "res-1")
        result = self.database.resolutions.apply_with_audit(
            resolution, discrepancy, DiscrepancyState.RESOLVED, current, next_reconciliation,
            AuditEvent("disc-event", "discrepancy", "disc-1", AuditEventType.RESOLUTION_APPLIED, "system", NOW, 1, "resolution_v1"),
            AuditEvent("rec-event", "reconciliation", "rec-2", AuditEventType.RESOLUTION_APPLIED, "system", NOW, 1, "resolution_v1", reconciliation_id="rec-2"),
            AuditEvent("res-event", "resolution", "res-1", AuditEventType.RESOLUTION_APPLIED, "system", NOW, 1, "resolution_v1"),
        )
        self.assertEqual(result[0], resolution)
        self.assertEqual(self.database.discrepancies.get("disc-1").state, DiscrepancyState.RESOLVED)
        self.assertEqual(self.database.reconciliations.get("rec-2"), next_reconciliation)
        self.assertEqual(self.database.audit_events.list_for_entity("resolution", "res-1")[0].sequence, 1)

    def test_state_and_audit_commit_or_rollback_together(self) -> None:
        event = AuditEvent("event-2", "batch", "batch-1", AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "foundation_v1",
                           previous_state="RECEIVED", new_state="VALIDATING", batch_id="batch-1")
        with self.assertRaises(RuntimeError):
            with self.database.transaction():
                self.database.batches.transition_with_audit(self.batch, BatchState.VALIDATING, event)
                raise RuntimeError("forced rollback")
        self.assertEqual(self.database.batches.get("batch-1").state, BatchState.RECEIVED)
        self.assertIsNone(self.database.audit_events.get("event-2"))
        committed = self.database.batches.transition_with_audit(self.batch, BatchState.VALIDATING, event)
        self.assertEqual(committed.state, BatchState.VALIDATING)
        self.assertIsNotNone(self.database.audit_events.get("event-2"))

    def test_processing_attempt_transition_is_atomic_with_audit(self) -> None:
        attempt = ProcessingAttempt("attempt-1", "batch-1", "processing_v1")
        self.database.processing_attempts.save(attempt)
        running = attempt.transition_to(ProcessingAttemptState.RUNNING, at=NOW)
        event = AuditEvent("attempt-event-1", "processing_attempt", "attempt-1", AuditEventType.BATCH_STATE_CHANGED, "system", NOW, 1, "processing_v1",
                           previous_state="CREATED", new_state="RUNNING", batch_id="batch-1", attempt_id="attempt-1")
        self.assertEqual(self.database.processing_attempts.transition_with_audit(attempt, ProcessingAttemptState.RUNNING, event, at=NOW), running)
        self.assertEqual(self.database.processing_attempts.get("attempt-1").state, ProcessingAttemptState.RUNNING)
        self.assertIsNotNone(self.database.audit_events.get("attempt-event-1"))

    def test_schema_rejects_orphan_records(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "INSERT INTO raw_records VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("raw-orphan", "missing", "batch-1", "A", "source_a.v1", "{}", HASH_A, NOW.isoformat(), None, None),
            )


if __name__ == "__main__":
    unittest.main()
