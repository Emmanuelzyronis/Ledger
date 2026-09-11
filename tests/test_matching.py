from datetime import datetime, timezone
import unittest

from ledger.candidates import CandidateGenerationService
from ledger.ingestion import RawIngestion
from ledger.matching import MatchingService
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])
        self.validation = ValidationService(self.db)
        self.normalization = NormalizationService(self.db)
        self.count = 0

    def tearDown(self):
        self.db.close()

    def add(self, source, record_id, *, reference=None, amount="10", date="2026-09-08"):
        self.count += 1
        schema = "source_a.v1" if source == "a" else "source_b.v1"
        payload = ({"record_id": record_id, "occurred_at": date, "amount": amount, "currency": "USD", "direction": "CREDIT"}
                   if source == "a" else {"id": record_id, "posted": date, "value": amount, "ccy": "USD", "side": "CREDIT"})
        if reference:
            payload["transaction_reference" if source == "a" else "reference"] = reference
        batch = self.ingestion.create_batch(source, f"external-{self.count}", schema, batch_id=f"batch-{self.count}", received_at=NOW)
        raw = self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        return self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)

    def evaluate(self):
        CandidateGenerationService(self.db).generate_all()
        return MatchingService(self.db).evaluate(evaluated_at=NOW)

    def test_precedence_and_replay(self):
        self.add("a", "a1", reference="R", amount="10")
        self.add("b", "b1", reference="R", amount="11")
        first = self.evaluate()
        self.assertEqual(first[0].outcome.value, "MISMATCHED")
        self.assertEqual(first[0].reconciliation.evidence["selected_rule"], "M-001")
        self.assertEqual(len(MatchingService(self.db).evaluate(evaluated_at=NOW)), 1)

    def test_ambiguity_and_unmatched_are_explicit(self):
        self.add("a", "a1", amount="10")
        self.add("b", "b1", amount="10")
        self.add("b", "b2", amount="10")
        decisions = self.evaluate()
        self.assertIn("AMBIGUOUS", [item.outcome.value for item in decisions])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 3)

    def test_one_to_one_conflict_is_duplicate(self):
        self.add("a", "a1", amount="10")
        self.add("a", "a2", reference="R2", amount="11")
        self.add("b", "b1", reference="R2", amount="10")
        decisions = self.evaluate()
        self.assertIn("DUPLICATE", {item.outcome.value for item in decisions})


if __name__ == "__main__":
    unittest.main()
