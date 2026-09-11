from datetime import datetime, timezone
import sqlite3
import unittest

from ledger.domain import Batch, BatchCounters, BatchState, RawRecord
from ledger.ingestion import RawIngestion, content_fingerprint
from ledger.observability import InMemoryTelemetrySink
from ledger.persistence import LedgerDatabase
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.telemetry = InMemoryTelemetrySink()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])
        self.validation = ValidationService(self.db, self.telemetry)

    def tearDown(self):
        self.db.close()

    def ingest(self, schema="source_a.v1", payload=None):
        source = "a" if schema == "source_a.v1" else "b"
        batch = self.ingestion.create_batch(source, "external-" + source, schema, batch_id="batch-" + source, received_at=NOW)
        default = {"record_id": "A-1", "occurred_at": "2026-09-08T10:00:00+00:00", "amount": "10.2500", "currency": "USD", "direction": "CREDIT"}
        result = self.ingestion.ingest(batch.batch_id, default if payload is None else payload, accepted_at=NOW)
        return batch, result

    def test_valid_source_a_and_b_records(self):
        _, a = self.ingest()
        batch_b = self.ingestion.create_batch("b", "external-b", "source_b.v1", batch_id="batch-b", received_at=NOW)
        b = self.ingestion.ingest(batch_b.batch_id, {"id": "B-1", "posted": "2026-09-08", "value": "-2.5", "ccy": "EUR", "side": "DEBIT", "memo": "original"}, accepted_at=NOW)
        self.assertEqual(self.validation.validate_record(a.raw_record_id, validated_at=NOW).status, "VALID")
        self.assertEqual(self.validation.validate_record(b.raw_record_id, validated_at=NOW).status, "VALID")

    def test_structural_semantic_and_business_errors_are_stable(self):
        payload = {"record_id": "", "occurred_at": "2026-02-30", "amount": "1,00", "currency": "usd", "direction": "SIDEWAYS", "extra": 1}
        _, ingested = self.ingest(payload=payload)
        first = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        second = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        self.assertEqual(first, second)
        self.assertEqual([(e["field"], e["code"]) for e in first.errors], [("extra", "unknown_field"), ("amount", "amount"), ("currency", "currency"), ("direction", "direction"), ("occurred_at", "date"), ("record_id", "empty")])

    def test_missing_and_malformed_fields_are_collected(self):
        _, ingested = self.ingest(payload={"record_id": "A-1", "occurred_at": 3, "amount": [], "currency": None, "direction": "CREDIT"})
        result = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        self.assertEqual(result.status, "INVALID")
        self.assertEqual([(e["field"], e["code"]) for e in result.errors], [("amount", "type"), ("currency", "type"), ("occurred_at", "type")])

    def test_invalid_raw_is_preserved_and_no_canonical_is_created(self):
        payload = {"record_id": "A-1", "occurred_at": "bad", "amount": "10", "currency": "USD", "direction": "CREDIT"}
        _, ingested = self.ingest(payload=payload)
        result = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        self.assertEqual(self.db.raw_records.get(ingested.raw_record_id).payload, payload)
        self.assertEqual(result.status, "INVALID")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM canonical_transactions").fetchone()[0], 0)

    def test_retry_does_not_duplicate_result_counter_or_audit(self):
        batch, ingested = self.ingest(payload={"record_id": "A-1", "occurred_at": "bad", "amount": "10", "currency": "USD", "direction": "CREDIT"})
        first = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        second = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        self.assertEqual(first.validation_id, second.validation_id)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.invalid_count, 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM validation_results").fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = 'RECORD_VALIDATED'").fetchone()[0], 1)

    def test_validation_persistence_failure_leaves_no_counter_or_audit(self):
        batch, ingested = self.ingest()
        original = self.db.validation_results.save
        self.db.validation_results.save = lambda result: (_ for _ in ()).throw(RuntimeError("injected persistence failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        finally:
            self.db.validation_results.save = original
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.processed_count, 0)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM validation_results").fetchone()[0], 0)

    def test_audit_failure_rolls_back_result_and_counter(self):
        batch, ingested = self.ingest(payload={"record_id": "A-1", "occurred_at": "bad", "amount": "10", "currency": "USD", "direction": "CREDIT"})
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("injected audit failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        finally:
            self.db.audit_events.append = original
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.invalid_count, 0)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM validation_results").fetchone()[0], 0)

    def test_batch_validation_transitions_and_counts_invalid_once(self):
        batch, _ = self.ingest(payload={"record_id": "A-1", "occurred_at": "bad", "amount": "10", "currency": "USD", "direction": "CREDIT"})
        results = self.validation.validate_batch(batch.batch_id)
        current = self.db.batches.get(batch.batch_id)
        self.assertEqual(current.state, BatchState.VALIDATED)
        self.assertEqual((current.counters.invalid_count, current.counters.processed_count), (1, 1))
        self.assertEqual(results[0].status, "INVALID")

    def test_layer_four_invalid_identifier_is_not_double_counted(self):
        batch, ingested = self.ingest(payload={"amount": "10"})
        self.assertEqual(ingested.status, "INVALID")
        result = self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        counters = self.db.batches.get(batch.batch_id).counters
        self.assertEqual(result.status, "INVALID")
        self.assertEqual((counters.invalid_count, counters.processed_count), (1, 1))

    def test_unsupported_schema_is_explicit(self):
        source = self.db.sources.get("a")
        raw_payload = {"record_id": "A-1"}
        self.db.connection.execute("PRAGMA foreign_keys = OFF")
        try:
            batch = Batch("batch-unknown", source.source_id, "unknown", "source_x.v1", NOW, counters=BatchCounters(received_count=1, accepted_count=1))
            self.db.batches.save(batch)
            raw = RawRecord("raw-unknown", "a", batch.batch_id, "A-1", "source_x.v1", raw_payload, content_fingerprint(raw_payload), NOW)
            self.db.raw_records.save(raw)
        finally:
            self.db.connection.execute("PRAGMA foreign_keys = ON")
        result = self.validation.validate_record("raw-unknown", validated_at=NOW)
        self.assertEqual(result.errors[0]["code"], "unsupported_schema")

    def test_validation_telemetry_contains_ids_without_payload(self):
        _, ingested = self.ingest()
        self.validation.validate_record(ingested.raw_record_id, validated_at=NOW)
        event = self.telemetry.events[-1]
        self.assertEqual(event["context"]["record_id"], ingested.raw_record_id)
        self.assertNotIn("payload", event["attributes"])


if __name__ == "__main__":
    unittest.main()
