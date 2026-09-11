from datetime import datetime, timezone
from decimal import Decimal
import unittest

from ledger.domain import CanonicalTransaction, Direction
from ledger.identity import (
    IdentityService,
    audit_event_identity,
    canonical_fingerprint,
    canonical_identity,
    canonical_serialization,
    raw_fingerprint,
    raw_identity,
    source_identity,
)
from ledger.ingestion import RawIngestion
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])
        self.validation = ValidationService(self.db)
        self.normalization = NormalizationService(self.db)

    def tearDown(self):
        self.db.close()

    def canonical(self, source="a", record_id="A-1", amount="10.0000"):
        schema = "source_a.v1" if source == "a" else "source_b.v1"
        payload = ({"record_id": record_id, "occurred_at": "2026-09-08", "amount": amount, "currency": "USD", "direction": "CREDIT"}
                   if source == "a" else {"id": record_id, "posted": "2026-09-08", "value": amount, "ccy": "USD", "side": "CREDIT"})
        batch = self.ingestion.create_batch(source, "external-" + source + record_id, schema, batch_id="batch-" + source + record_id, received_at=NOW)
        raw = self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        return self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)

    def test_identity_vectors_are_namespaced_and_stable(self):
        payload_a = {"b": "x", "a": "Cafe\u0301"}
        payload_b = {"a": "Caf\u00e9", "b": "x"}
        self.assertEqual(raw_fingerprint(payload_a), raw_fingerprint(payload_b))
        self.assertEqual(raw_identity("a", "source_a.v1", payload_a), "raw:a:source_a.v1:" + raw_fingerprint(payload_a))
        self.assertEqual(source_identity("a", "1"), "src:a:1")
        self.assertNotEqual(source_identity("a", "1"), source_identity("b", "1"))
        self.assertEqual(canonical_identity("raw:x", "canonical_v2", 1), "can:raw:x:canonical_v2:1")
        self.assertEqual(audit_event_identity("NORMALIZATION_COMPLETED", "canonical_transaction", "can:x", None, "canonical_v2", 1), audit_event_identity("NORMALIZATION_COMPLETED", "canonical_transaction", "can:x", None, "canonical_v2", 1))

    def test_canonical_fingerprint_ignores_provenance_and_time_but_detects_semantic_change(self):
        one = CanonicalTransaction("can:r:v:1", "a", "r", "A", NOW, Decimal("1"), "USD", Direction.CREDIT, "v", 1, "0" * 64, NOW, description="x")
        two = CanonicalTransaction("can:r2:v:9", "b", "r2", "B", NOW, Decimal("1.0000"), "USD", Direction.CREDIT, "v", 9, "0" * 64, NOW.replace(year=2031), description="x")
        three = CanonicalTransaction("can:r3:v:1", "a", "r3", "C", NOW, Decimal("2"), "USD", Direction.CREDIT, "v", 1, "0" * 64, NOW, description="x")
        self.assertEqual(canonical_fingerprint(one), canonical_fingerprint(two))
        self.assertNotEqual(canonical_fingerprint(one), canonical_fingerprint(three))
        self.assertEqual(canonical_serialization(one), canonical_serialization(two))

    def test_identity_service_is_idempotent_and_preserves_source_lineage(self):
        transaction = self.canonical()
        service = IdentityService(self.db)
        first = service.identify(transaction.canonical_id)
        second = service.identify(transaction.canonical_id)
        self.assertEqual(first, second)
        self.assertEqual(first.source_identity, "src:a:A-1")
        self.assertEqual(first.raw_identity, transaction.raw_record_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM canonical_transactions").fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 0)

    def test_different_sources_with_same_native_id_remain_distinct(self):
        a = self.canonical("a", "same")
        b = self.canonical("b", "same")
        self.assertNotEqual(a.canonical_id, b.canonical_id)
        self.assertNotEqual(a.raw_record_id, b.raw_record_id)
        self.assertNotEqual(source_identity(a.source_id, a.source_record_id), source_identity(b.source_id, b.source_record_id))

    def test_canonical_repository_replay_is_idempotent_and_collision_conscious(self):
        transaction = self.canonical()
        persisted = self.db.canonical_transactions.save(transaction)
        self.assertEqual(persisted, transaction)
        altered = CanonicalTransaction(transaction.canonical_id, transaction.source_id, transaction.raw_record_id, transaction.source_record_id, transaction.occurred_at, Decimal("11"), transaction.currency, transaction.direction, transaction.normalization_version, transaction.canonical_version, transaction.canonical_fingerprint, transaction.created_at)
        with self.assertRaises(Exception):
            self.db.canonical_transactions.save(altered)


if __name__ == "__main__":
    unittest.main()
