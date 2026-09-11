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


if __name__ == "__main__":
    unittest.main()
