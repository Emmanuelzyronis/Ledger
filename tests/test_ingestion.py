from datetime import datetime, timezone
import sqlite3
import unittest

from ledger.ingestion import RawIngestion
from ledger.observability import InMemoryTelemetrySink
from ledger.persistence import LedgerDatabase


NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.telemetry = InMemoryTelemetrySink()
        self.ingestion = RawIngestion(self.db, self.telemetry)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])

    def tearDown(self):
        self.db.close()

    def test_both_source_envelopes_and_cross_batch_reuse(self):
        a = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        b = self.ingestion.create_batch("b", "one", "source_b.v1", batch_id="bb", received_at=NOW)
        ra = self.ingestion.ingest(a.batch_id, {"record_id": "A-1", "amount": "10.00"}, accepted_at=NOW)
        rb = self.ingestion.ingest(b.batch_id, {"id": "B-1", "value": "10.00"}, accepted_at=NOW)
        self.assertNotEqual(ra.raw_record_id, rb.raw_record_id)
        second = self.ingestion.create_batch("a", "two", "source_a.v1", batch_id="ba2", received_at=NOW)
        replay = self.ingestion.ingest(second.batch_id, {"record_id": "A-1", "amount": "10.00"}, accepted_at=NOW)
        self.assertEqual(replay.raw_record_id, ra.raw_record_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0], 2)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM raw_record_batches WHERE raw_record_id = ?", (ra.raw_record_id,)).fetchone()[0], 2)

    def test_correction_is_new_immutable_raw_version(self):
        batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        first = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "amount": "10.00"}, accepted_at=NOW)
        corrected = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "amount": "11.00"}, accepted_at=NOW)
        self.assertNotEqual(first.raw_record_id, corrected.raw_record_id)
        row = self.db.connection.execute("SELECT supersedes_raw_record_id FROM raw_records WHERE raw_record_id = ?", (corrected.raw_record_id,)).fetchone()
        self.assertEqual(row[0], first.raw_record_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.connection.execute("UPDATE raw_records SET invalid_reason = 'x' WHERE raw_record_id = ?", (first.raw_record_id,))

    def test_invalid_envelopes_are_explicit_and_rejected_inputs_counted(self):
        batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        invalid = self.ingestion.ingest(batch.batch_id, {"amount": "10.00"}, accepted_at=NOW)
        rejected = self.ingestion.ingest(batch.batch_id, ["not", "an", "object"], accepted_at=NOW)
        self.assertEqual(invalid.status, "INVALID")
        self.assertEqual(rejected.status, "REJECTED")
        counters = self.db.batches.get(batch.batch_id).counters
        self.assertEqual((counters.received_count, counters.accepted_count, counters.rejected_input_count, counters.invalid_count), (2, 1, 1, 1))

    def test_explicit_retry_is_idempotent(self):
        batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        first = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1"}, idempotency_key="request-1", accepted_at=NOW)
        retry = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "amount": "changed"}, idempotency_key="request-1", accepted_at=NOW)
        self.assertTrue(retry.duplicate_submission)
        self.assertEqual(first.raw_record_id, retry.raw_record_id)
        self.assertEqual(self.db.batches.get(batch.batch_id).counters.received_count, 1)

    def test_canonical_equivalent_payloads_replay_without_mutating_first_evidence(self):
        batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        first_payload = {"record_id": "A-1", "description": "caf\u0065\u0301\r\n", "amount": "1"}
        equivalent_payload = {"amount": "1", "description": "caf\u00e9\n", "record_id": "A-1"}
        first = self.ingestion.ingest(batch.batch_id, first_payload, accepted_at=NOW)
        replay = self.ingestion.ingest(batch.batch_id, equivalent_payload, accepted_at=NOW)
        self.assertEqual(first.raw_record_id, replay.raw_record_id)
        self.assertTrue(replay.duplicate_submission)
        self.assertEqual(self.db.raw_records.get(first.raw_record_id).payload["description"], "caf\u0065\u0301\r\n")
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = 'SUBMISSION_DUPLICATE'").fetchone()[0], 1)

    def test_genuinely_different_canonical_content_does_not_collapse(self):
        batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        first = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "amount": "1"}, accepted_at=NOW)
        second = self.ingestion.ingest(batch.batch_id, {"record_id": "A-1", "amount": "2"}, accepted_at=NOW)
        self.assertNotEqual(first.raw_record_id, second.raw_record_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0], 2)

    def test_duplicate_audit_failure_rolls_back_replay_association(self):
        first_batch = self.ingestion.create_batch("a", "one", "source_a.v1", batch_id="ba", received_at=NOW)
        second_batch = self.ingestion.create_batch("a", "two", "source_a.v1", batch_id="bb", received_at=NOW)
        first = self.ingestion.ingest(first_batch.batch_id, {"record_id": "A-1", "amount": "1"}, accepted_at=NOW)
        before = self.db.connection.execute("SELECT COUNT(*) FROM raw_record_batches WHERE raw_record_id = ?", (first.raw_record_id,)).fetchone()[0]
        original = self.db.audit_events.append
        self.db.audit_events.append = lambda event: (_ for _ in ()).throw(RuntimeError("injected audit failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.ingestion.ingest(second_batch.batch_id, {"amount": "1", "record_id": "A-1"}, accepted_at=NOW)
        finally:
            self.db.audit_events.append = original
        after = self.db.connection.execute("SELECT COUNT(*) FROM raw_record_batches WHERE raw_record_id = ?", (first.raw_record_id,)).fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
