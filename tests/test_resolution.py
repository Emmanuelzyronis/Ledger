from datetime import datetime, timezone
import sqlite3
import unittest
from decimal import Decimal

from ledger.domain import Batch, CanonicalTransaction, Direction, Discrepancy, Reconciliation, ReconciliationOutcome, ReconciliationState, ResolutionType, Source, RawRecord
from ledger.persistence import LedgerDatabase
from ledger.resolution import ResolutionService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class ResolutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.db.sources.save(Source("a", "A", ("v1",)))
        self.db.batches.save(Batch("batch", "a", "external", "v1", NOW))
        self.db.raw_records.save(RawRecord("raw-a", "a", "batch", "A", "v1", {"id": "A"}, "a" * 64, NOW))
        self.db.raw_records.save(RawRecord("raw-b", "a", "batch", "B", "v1", {"id": "B"}, "b" * 64, NOW))
        self.db.canonical_transactions.save(CanonicalTransaction("can-a", "a", "raw-a", "A", NOW, Decimal("1"), "USD", Direction.CREDIT, "v1", 1, "c" * 64, NOW))
        self.db.canonical_transactions.save(CanonicalTransaction("can-b", "a", "raw-b", "B", NOW, Decimal("1"), "USD", Direction.CREDIT, "v1", 1, "d" * 64, NOW))
        self.rec = Reconciliation("rec", "batch", "can-a", "can-b", 1, "standard_v1", {"rule": "M-001"},
                                   ReconciliationState.MISMATCHED, ReconciliationOutcome.MISMATCHED)
        self.db.reconciliations.save(self.rec)
        self.db.discrepancies.save(Discrepancy("disc", "rec", "amount differs"))
        self.service = ResolutionService(self.db)

    def tearDown(self):
        self.db.close()

    def test_manual_approval_is_authorized_immutable_and_idempotent(self):
        with self.assertRaises(PermissionError):
            self.service.resolve("disc", ResolutionType.MANUAL_APPROVED, actor="other", reason="no")
        first = self.service.resolve("disc", ResolutionType.MANUAL_APPROVED, actor="reconciliation_operator", reason="verified", created_at=NOW)
        second = self.service.resolve("disc", ResolutionType.MANUAL_APPROVED, actor="reconciliation_operator", reason="verified", created_at=NOW)
        self.assertEqual(first, second)
        self.assertEqual(first.reconciliation.state, ReconciliationState.RESOLVED)
        self.assertEqual(first.discrepancy.state.value, "RESOLVED")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM resolutions").fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 2)
        self.assertEqual([e.sequence for e in self.db.audit_events.list_for_entity("resolution", first.resolution.resolution_id)], [1])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.connection.execute("UPDATE resolutions SET reason = 'changed'")

    def test_deferred_and_rejected_preserve_reconciliation_outcome(self):
        deferred = self.service.resolve("disc", ResolutionType.DEFERRED, actor="reconciliation_operator", reason="awaiting evidence", created_at=NOW)
        self.assertEqual(deferred.discrepancy.state.value, "DEFERRED")
        self.assertEqual(deferred.reconciliation, self.rec)
        repeated = self.service.resolve("disc", ResolutionType.REJECTED, actor="reconciliation_operator", reason="second decision", created_at=NOW)
        self.assertEqual(repeated.resolution.resolution_type, ResolutionType.DEFERRED)

    def test_automatic_requires_system_and_rule_version(self):
        with self.assertRaises(PermissionError):
            self.service.resolve("disc", ResolutionType.AUTOMATIC, actor="reconciliation_operator", reason="rule")
        result = self.service.resolve("disc", ResolutionType.AUTOMATIC, actor="system", reason="rule", rule_version="auto_v1", created_at=NOW)
        self.assertEqual(result.reconciliation.state, ReconciliationState.RESOLVED)

    def test_audit_failure_rolls_back_all_resolution_state(self):
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("audit failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.service.resolve("disc", ResolutionType.MANUAL_APPROVED, actor="reconciliation_operator", reason="verified", created_at=NOW)
        finally:
            self.db.audit_events.append = original
        self.assertIsNone(self.db.resolutions.get("resolution:" + "x" * 64))
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM resolutions").fetchone()[0], 0)
        self.assertEqual(self.db.discrepancies.get("disc").state.value, "OPEN")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
