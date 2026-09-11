from datetime import datetime, timezone
from decimal import Decimal
import unittest

from ledger.domain import Batch, CanonicalTransaction, Direction, ReconciliationOutcome, Source, RawRecord
from ledger.persistence import LedgerDatabase
from ledger.reconciliation import ReconciliationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.db.sources.save(Source("a", "A", ("v1",)))
        self.db.sources.save(Source("b", "B", ("v1",)))
        self.db.batches.save(Batch("batch", "a", "external", "v1", NOW))
        self.db.raw_records.save(RawRecord("raw", "a", "batch", "native", "v1", {"x": 1}, "a" * 64, NOW))
        self.db.batches.save(Batch("batch-b", "b", "external-b", "v1", NOW))
        self.db.raw_records.save(RawRecord("raw-b", "b", "batch-b", "native-b", "v1", {"x": 2}, "b" * 64, NOW))
        self.db.canonical_transactions.save(CanonicalTransaction("can-a", "a", "raw", "native", NOW, Decimal("1"), "USD", Direction.CREDIT, "v1", 1, "c" * 64, NOW))
        self.db.canonical_transactions.save(CanonicalTransaction("can-b", "b", "raw-b", "native-b", NOW, Decimal("2"), "USD", Direction.CREDIT, "v1", 1, "d" * 64, NOW))
        self.db.canonical_transactions.save(CanonicalTransaction("can-c", "b", "raw-b", "native-b-2", NOW, Decimal("3"), "USD", Direction.CREDIT, "v1", 2, "e" * 64, NOW))

    def tearDown(self):
        self.db.close()

    def test_invalid_is_raw_only_and_replay_is_idempotent(self):
        service = ReconciliationService(self.db)
        first = service.reconcile_invalid("raw")
        second = service.reconcile_invalid("raw")
        self.assertEqual(first, second)
        self.assertEqual(first.outcome, ReconciliationOutcome.INVALID)
        self.assertEqual(first.raw_record_id, "raw")
        self.assertIsNone(first.source_a_record_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 1)

    def test_late_arrival_creates_linked_superseding_version(self):
        service = ReconciliationService(self.db)
        original = service.persist_decision(batch_id="batch", source_a_record_id="can-a",
                                            outcome=ReconciliationOutcome.UNMATCHED_A,
                                            evidence={}, evaluated_at=NOW)
        self.assertEqual(original.reconciliation_version, 1)
        self.assertIsNone(original.supersedes_reconciliation_id)
        late = service.persist_decision(batch_id="batch", source_a_record_id="can-a",
                                        source_b_record_id="can-b",
                                        outcome=ReconciliationOutcome.MATCHED, evidence={}, evaluated_at=NOW)
        self.assertEqual(late.reconciliation_version, 2)
        self.assertEqual(late.supersedes_reconciliation_id, original.reconciliation_id)
        self.assertNotEqual(late.reconciliation_id, original.reconciliation_id)
        # Replaying the same content returns the existing version, not a new one.
        self.assertEqual(service.persist_decision(batch_id="batch", source_a_record_id="can-a",
                                                  source_b_record_id="can-b",
                                                  outcome=ReconciliationOutcome.MATCHED,
                                                  evidence={}, evaluated_at=NOW), late)
        # The superseded version is preserved and no longer current.
        self.assertEqual(self.db.reconciliations.get(original.reconciliation_id), original)
        current_ids = {row.reconciliation_id for row in self.db.reconciliations.list_current()}
        self.assertIn(late.reconciliation_id, current_ids)
        self.assertNotIn(original.reconciliation_id, current_ids)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 2)

    def test_unrelated_scope_does_not_supersede(self):
        # A correction-like change of participant must not supersede an
        # unrelated existing decision: {can-a, can-b} is not a subset of
        # {can-c, can-b}.
        service = ReconciliationService(self.db)
        pair = service.persist_decision(batch_id="batch", source_a_record_id="can-a",
                                        source_b_record_id="can-b",
                                        outcome=ReconciliationOutcome.MATCHED, evidence={}, evaluated_at=NOW)
        other = service.persist_decision(batch_id="batch", source_a_record_id="can-c",
                                         source_b_record_id="can-b",
                                         outcome=ReconciliationOutcome.UNMATCHED_A, evidence={}, evaluated_at=NOW)
        self.assertEqual(other.reconciliation_version, 1)
        self.assertIsNone(other.supersedes_reconciliation_id)
        self.assertEqual(pair.reconciliation_version, 1)
        self.assertIsNone(pair.supersedes_reconciliation_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 2)

    def test_invalid_decisions_do_not_supersede_each_other(self):
        service = ReconciliationService(self.db)
        first = service.reconcile_invalid("raw")
        self.assertEqual(first.reconciliation_version, 1)
        self.assertIsNone(first.supersedes_reconciliation_id)

    def test_mismatch_and_ambiguity_create_discrepancy(self):
        service = ReconciliationService(self.db)
        for outcome, counterpart in ((ReconciliationOutcome.MISMATCHED, "can-b"), (ReconciliationOutcome.AMBIGUOUS, "can-c")):
            rec = service.persist_decision(batch_id="batch", source_a_record_id="can-a", source_b_record_id=counterpart,
                                            outcome=outcome, evidence={}, evaluated_at=NOW)
            self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM discrepancies WHERE reconciliation_id = ?", (rec.reconciliation_id,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
