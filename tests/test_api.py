import unittest

from ledger.api import LedgerAPI
from ledger.observability import InMemoryTelemetrySink
from ledger.persistence import LedgerDatabase


class APITests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.telemetry = InMemoryTelemetrySink()
        self.api = LedgerAPI(self.db, telemetry=self.telemetry,
                             token_verifier=lambda token: ({"roles": ["reconciliation_operator"], "source_ids": ["source"]}
                                                           if token == "valid" else None))
        self.headers = {"Authorization": "Bearer valid", "X-Correlation-ID": "test-correlation"}

    def tearDown(self):
        self.db.close()

    def test_authentication_and_source_batch_record_idempotency(self):
        status, _ = self.api.handle("GET", "/health")
        self.assertEqual(status, 401)
        status, _ = self.api.handle("POST", "/sources", {"source_id": "source", "name": "Source", "schema_versions": ["source_a.v1"]}, self.headers)
        self.assertEqual(status, 200)
        status, batch = self.api.handle("POST", "/batches", {"source_id": "source", "external_batch_id": "external", "schema_version": "source_a.v1"}, self.headers)
        self.assertEqual(status, 200)
        batch_id = batch["data"]["batch_id"]
        record = {"record_id": "r1", "occurred_at": "2026-09-08", "amount": "1.00", "currency": "USD", "direction": "CREDIT"}
        first = self.api.handle("POST", f"/batches/{batch_id}/records", {"payload": record, "idempotency_key": "key"}, self.headers)
        second = self.api.handle("POST", f"/batches/{batch_id}/records", {"payload": record, "idempotency_key": "key"}, self.headers)
        self.assertEqual(first[0], 200)
        self.assertEqual(second[0], 200)
        self.assertFalse(first[1]["data"]["duplicate_submission"])
        self.assertTrue(second[1]["data"]["duplicate_submission"])

    def test_scoped_reporting_and_health_correlation(self):
        status, response = self.api.handle("GET", "/reports", headers=self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["source_watermark"]["event_count"], 0)
        self.assertEqual(response["correlation_id"], "test-correlation")
        self.assertEqual(self.telemetry.events[-1]["attributes"]["status"], 200)

    def test_identical_content_with_a_new_key_returns_duplicate_not_an_error(self):
        self.api.handle("POST", "/sources", {"source_id": "source", "name": "Source", "schema_versions": ["source_a.v1"]}, self.headers)
        _, batch = self.api.handle("POST", "/batches", {"source_id": "source", "external_batch_id": "external", "schema_version": "source_a.v1"}, self.headers)
        batch_id = batch["data"]["batch_id"]
        record = {"record_id": "r1", "occurred_at": "2026-09-08", "amount": "1.00", "currency": "USD", "direction": "CREDIT"}
        first = self.api.handle("POST", f"/batches/{batch_id}/records", {"payload": record, "idempotency_key": "key-1"}, self.headers)
        reused = self.api.handle("POST", f"/batches/{batch_id}/records", {"payload": record, "idempotency_key": "key-2"}, self.headers)
        self.assertEqual(first[0], 200)
        self.assertEqual(reused[0], 200)
        self.assertFalse(first[1]["data"]["duplicate_submission"])
        self.assertTrue(reused[1]["data"]["duplicate_submission"])
        self.assertEqual(first[1]["data"]["raw_record_id"], reused[1]["data"]["raw_record_id"])
        self.assertEqual(self.count("raw_records"), 1)
        self.assertEqual(self.count("raw_record_batches"), 1)
        self.assertEqual(self.count("audit_events", "event_type = 'RECORD_INGESTED'"), 1)
        self.assertEqual(self.count("audit_events", "event_type = 'SUBMISSION_DUPLICATE'"), 1)
        self.assertEqual(self.db.batches.get(batch_id).counters.received_count, 1)

    def count(self, table: str, where: str | None = None) -> int:
        query = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
        return self.db.connection.execute(query).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
