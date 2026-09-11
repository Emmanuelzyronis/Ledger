from datetime import datetime, timezone
from decimal import Decimal
import json
import sqlite3
import unittest

from ledger.domain import BatchCounters
from ledger.ingestion import RawIngestion
from ledger.normalization import NormalizationService
from ledger.observability import InMemoryTelemetrySink
from ledger.persistence import LedgerDatabase
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.telemetry = InMemoryTelemetrySink()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])
        self.validation = ValidationService(self.db)
        self.normalization = NormalizationService(self.db, self.telemetry)

    def tearDown(self):
        self.db.close()

    def ingest_valid(self, schema="source_a.v1", payload=None, suffix="1"):
        source = "a" if schema == "source_a.v1" else "b"
        batch = self.ingestion.create_batch(source, "external-" + suffix, schema, batch_id="batch-" + suffix, received_at=NOW)
        defaults = {"record_id": "A-1", "occurred_at": "2026-09-08T12:30:00+02:00", "amount": "10.25", "currency": "USD", "direction": "CREDIT", "account_reference": " acct ", "transaction_reference": " ref ", "description": " Cafe\u0301 ", "transaction_type": " payment "}
        if schema == "source_b.v1":
            defaults = {"id": "B-1", "posted": "2026-09-08", "value": "10.2500", "ccy": "EUR", "side": "DEBIT", "account_ref": "acct", "reference": "ref", "memo": "memo", "type": "refund"}
        result = self.ingestion.ingest(batch.batch_id, defaults if payload is None else payload, accepted_at=NOW)
        self.validation.validate_record(result.raw_record_id, validated_at=NOW)
        return batch, result

    def test_source_a_mapping_and_canonical_fields(self):
        _, raw = self.ingest_valid()
        result = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        self.assertEqual((result.source_id, result.source_record_id), ("a", "A-1"))
        self.assertEqual(result.occurred_at, datetime(2026, 9, 8, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(result.amount, Decimal("10.2500"))
        self.assertEqual((result.account_reference, result.transaction_reference, result.description, result.transaction_type), ("acct", "ref", "Café", "payment"))
        self.assertEqual(result.normalization_version, "canonical_v2")

    def test_source_b_mapping_and_date_normalization(self):
        _, raw = self.ingest_valid("source_b.v1")
        result = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        self.assertEqual((result.source_record_id, result.currency, result.direction.value), ("B-1", "EUR", "DEBIT"))
        self.assertEqual(result.occurred_at, datetime(2026, 9, 8, tzinfo=timezone.utc))

    def test_replay_is_idempotent_and_serialization_stable(self):
        _, raw = self.ingest_valid()
        first = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        second = self.normalization.normalize_record(raw.raw_record_id, created_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first.semantic_payload(), sort_keys=True, separators=(",", ":")), json.dumps(second.semantic_payload(), sort_keys=True, separators=(",", ":")))
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM canonical_transactions").fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='NORMALIZATION_COMPLETED'").fetchone()[0], 1)

    def test_equivalent_amount_date_and_unicode_have_same_fingerprint(self):
        p1 = {"record_id": "A-1", "occurred_at": "2026-09-08T10:00:00+00:00", "amount": "1", "currency": "USD", "direction": "CREDIT", "description": "Cafe\u0301"}
        p2 = {"direction": "CREDIT", "currency": "USD", "amount": "1.0000", "occurred_at": "2026-09-08T12:00:00+02:00", "record_id": "A-2", "description": "Café"}
        _, r1 = self.ingest_valid(payload=p1, suffix="eq1")
        _, r2 = self.ingest_valid(payload=p2, suffix="eq2")
        c1 = self.normalization.normalize_record(r1.raw_record_id, created_at=NOW)
        c2 = self.normalization.normalize_record(r2.raw_record_id, created_at=NOW)
        self.assertEqual(c1.canonical_fingerprint, c2.canonical_fingerprint)
        self.assertEqual(c1.semantic_payload(), c2.semantic_payload())

    def test_changed_version_creates_immutable_superseding_version(self):
        _, raw = self.ingest_valid()
        first = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        second = NormalizationService(self.db, normalization_version="canonical_v3").normalize_record(raw.raw_record_id, created_at=NOW)
        self.assertEqual((first.canonical_version, second.canonical_version), (1, 2))
        self.assertEqual(second.supersedes_canonical_id, first.canonical_id)
        self.assertEqual(len(self.db.canonical_transactions.list_for_raw(raw.raw_record_id)), 2)

    def test_invalid_record_is_preserved_and_classified_without_canonical(self):
        batch = self.ingestion.create_batch("a", "invalid", "source_a.v1", batch_id="batch-invalid", received_at=NOW)
        raw = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "occurred_at": "bad", "amount": "1", "currency": "USD", "direction": "CREDIT"}, accepted_at=NOW)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        before = self.db.raw_records.get(raw.raw_record_id)
        self.assertIsNone(self.normalization.normalize_record(raw.raw_record_id))
        self.assertEqual(self.db.raw_records.get(raw.raw_record_id), before)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM canonical_transactions").fetchone()[0], 0)
        event = self.db.connection.execute("SELECT metadata_json FROM audit_events WHERE event_type='NORMALIZATION_COMPLETED'").fetchone()
        self.assertEqual(json.loads(event[0])["failure_code"], "validation_invalid")

    def test_canonical_or_audit_failure_rolls_back_authoritative_writes(self):
        _, raw = self.ingest_valid()
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("audit failure"))
        try:
            with self.assertRaises(RuntimeError): self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM canonical_transactions").fetchone()[0], 0)

    def test_failure_counter_and_audit_roll_back_together(self):
        batch = self.ingestion.create_batch("a", "invalid", "source_a.v1", batch_id="batch-invalid", received_at=NOW)
        raw = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "occurred_at": "bad", "amount": "1", "currency": "USD", "direction": "CREDIT"}, accepted_at=NOW)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("audit failure"))
        try:
            with self.assertRaises(RuntimeError): self.normalization.normalize_record(raw.raw_record_id)
        finally:
            self.db.audit_events.append = original
        counters = self.db.batches.get(batch.batch_id).counters
        self.assertEqual(counters.failed_count, 0)

    def test_telemetry_is_structured_redacted_and_no_future_state_is_written(self):
        _, raw = self.ingest_valid()
        canonical = self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)
        event = self.telemetry.events[-1]
        self.assertEqual(event["context"], {"batch_id": "batch-1", "record_id": raw.raw_record_id})
        self.assertEqual(event["attributes"]["canonical_transaction_id"], canonical.canonical_id)
        self.assertNotIn("payload", event["attributes"])
        for table in ("match_candidates", "reconciliations", "discrepancies", "resolutions"):
            self.assertEqual(self.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
