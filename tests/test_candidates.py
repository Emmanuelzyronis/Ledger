from datetime import datetime, timezone
import unittest

from ledger.candidates import AMOUNT_DATE_INDEX, REFERENCE_INDEX, CandidateGenerationService
from ledger.ingestion import RawIngestion
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.validation import ValidationService


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


class CandidateGenerationTests(unittest.TestCase):
    def setUp(self):
        self.db = LedgerDatabase()
        self.ingestion = RawIngestion(self.db)
        self.ingestion.register_source("a", "A", ["source_a.v1"])
        self.ingestion.register_source("b", "B", ["source_b.v1"])
        self.validation = ValidationService(self.db)
        self.normalization = NormalizationService(self.db)
        self.generator = CandidateGenerationService(self.db)
        self.counter = 0

    def tearDown(self):
        self.db.close()

    def canonical(self, source, record_id, *, date="2026-09-08", amount="10", currency="USD", reference=None):
        self.counter += 1
        schema = "source_a.v1" if source == "a" else "source_b.v1"
        payload = ({"record_id": record_id, "occurred_at": date, "amount": amount, "currency": currency, "direction": "CREDIT"}
                   if source == "a" else {"id": record_id, "posted": date, "value": amount, "ccy": currency, "side": "CREDIT"})
        if reference:
            payload["transaction_reference" if source == "a" else "reference"] = reference
        batch = self.ingestion.create_batch(source, f"external-{source}-{self.counter}", schema, batch_id=f"batch-{source}-{self.counter}", received_at=NOW)
        raw = self.ingestion.ingest(batch.batch_id, payload, accepted_at=NOW)
        self.validation.validate_record(raw.raw_record_id, validated_at=NOW)
        return self.normalization.normalize_record(raw.raw_record_id, created_at=NOW)

    def test_union_completeness_and_exclusions(self):
        target = self.canonical("a", "A-1", reference="INV-1")
        by_reference = self.canonical("b", "B-REF", date="2026-01-01", amount="99", reference="INV-1")
        by_amount = self.canonical("b", "B-AMT", date="2026-09-10", amount="10")
        self.canonical("b", "B-WRONG-AMOUNT", amount="11")
        self.canonical("b", "B-WRONG-CURRENCY", currency="EUR")
        self.canonical("b", "B-OUTSIDE-WINDOW", date="2026-09-11", amount="10")
        candidates = self.generator.generate_for(target.canonical_id)
        self.assertEqual([c.source_b_canonical_id for c in candidates], sorted([by_reference.canonical_id, by_amount.canonical_id]))
        evidence = {c.source_b_canonical_id: c.evidence["indexes"] for c in candidates}
        self.assertEqual(evidence[by_reference.canonical_id], (REFERENCE_INDEX,))
        self.assertEqual(evidence[by_amount.canonical_id], (AMOUNT_DATE_INDEX,))

    def test_same_pair_hit_by_both_indexes_is_one_candidate_with_complete_evidence(self):
        target = self.canonical("a", "A-1", reference="INV-1")
        counterpart = self.canonical("b", "B-1", reference="INV-1")
        candidates = self.generator.generate_for(target.canonical_id)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].evidence["indexes"], (AMOUNT_DATE_INDEX, REFERENCE_INDEX))
        self.assertEqual(candidates[0].eligible_rule_ids, (AMOUNT_DATE_INDEX, REFERENCE_INDEX))
        self.assertEqual(candidates[0].source_b_canonical_id, counterpart.canonical_id)

    def test_deterministic_order_and_idempotent_persistence(self):
        target = self.canonical("a", "A-1")
        first_counterpart = self.canonical("b", "B-1", amount="10")
        second_counterpart = self.canonical("b", "B-2", amount="10")
        first = self.generator.generate_for(target.canonical_id)
        second = self.generator.generate_for(target.canonical_id)
        self.assertEqual([c.candidate_id for c in first], [c.candidate_id for c in second])
        self.assertEqual([c.source_b_canonical_id for c in first], sorted([first_counterpart.canonical_id, second_counterpart.canonical_id]))
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0], 2)

    def test_pair_is_idempotent_when_generated_from_either_source(self):
        left = self.canonical("a", "A-1")
        right = self.canonical("b", "B-1")
        from_b = self.generator.generate_for(right.canonical_id)
        from_a = self.generator.generate_for(left.canonical_id)
        self.assertEqual(from_a, from_b)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0], 1)

    def test_source_isolation_and_one_to_one_boundary(self):
        target = self.canonical("a", "same")
        self.canonical("a", "same-2", amount="10")
        other = self.canonical("b", "same", amount="10")
        candidates = self.generator.generate_for(target.canonical_id)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_b_canonical_id, other.canonical_id)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 0)

    def test_generate_all_is_bounded_by_index_probes_and_does_not_match(self):
        self.canonical("a", "A-1", date="2026-09-08", amount="10")
        self.canonical("b", "B-1", date="2026-09-10", amount="10")
        all_candidates = self.generator.generate_all()
        self.assertEqual(len(all_candidates), 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 0)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM discrepancies").fetchone()[0], 0)

    def test_persistence_failure_rolls_back_candidate_batch(self):
        target = self.canonical("a", "A-1")
        self.canonical("b", "B-1")
        original = self.db.match_candidates.save
        self.db.match_candidates.save = lambda candidate: (_ for _ in ()).throw(RuntimeError("injected candidate failure"))
        try:
            with self.assertRaises(RuntimeError):
                self.generator.generate_for(target.canonical_id)
        finally:
            self.db.match_candidates.save = original
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
