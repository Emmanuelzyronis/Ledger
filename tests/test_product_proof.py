"""Layer 15 product-proof regression suite (V5).

These tests execute the deterministic end-to-end product proof with real
services and real persistence and independently verify the externally
observable outcomes against authoritative state.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger.api import LedgerAPI
from ledger.domain import DiscrepancyState, ReconciliationState, ResolutionType
from ledger.persistence import LedgerDatabase

from product_proof import dataset
from product_proof.pipeline import (
    evaluate_matching,
    generate_candidates,
    normalize_raw_ids,
    record_outcomes,
    register_sources,
    row_count,
    run_standard_pipeline,
    seed_records,
    validate_batches,
    verify_identities,
)
from product_proof.runner import (
    _all_reconciliation_rows,
    _row_names,
    _discrepancy_table,
    _raw_payload_values,
    _token_verifier,
    database_signature,
    outcome_count_values,
    pipeline_decisions,
    run_correction,
    run_full_proof,
    run_portfolio,
    run_restart,
    run_telemetry,
)
from ledger.ingestion import RawIngestion


def _all_checks_pass(results: dict) -> bool:
    return all(check["passed"] for check in results["checks"])


class PortfolioProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = run_portfolio()
        self.observations = self.result["observations"]

    def test_all_checks_pass(self) -> None:
        self.assertTrue(_all_checks_pass(self.result), [c for c in self.result["checks"] if not c["passed"]])

    def test_every_record_reaches_its_expected_outcome(self) -> None:
        observed = self.observations["record_outcomes"]
        self.assertEqual(observed, dataset.EXPECTED_PORTFOLIO_OUTCOMES)

    def test_all_seven_reconciliation_outcomes_are_demonstrated(self) -> None:
        self.assertEqual(self.observations["initial_decision_counts"],
                         {"MATCHED": 2, "MISMATCHED": 2, "UNMATCHED_A": 1, "AMBIGUOUS": 3,
                          "UNMATCHED_B": 1, "DUPLICATE": 3, "INVALID": 1})

    def test_matched_pairs_are_explainable_via_m001(self) -> None:
        db = LedgerDatabase()
        try:
            ingestion = RawIngestion(db)
            register_sources(ingestion)
            batch_a, _ = seed_records(db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                                      batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
            batch_b, _ = seed_records(db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                                      batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
            run_standard_pipeline(db, [batch_a, batch_b], reconcile_invalid=True)
            rows = _all_reconciliation_rows(db)
            for row in rows:
                if row["outcome"] not in {"MATCHED", "MISMATCHED"}:
                    continue
                self.assertEqual(row["evidence"]["rule_version"], dataset.RULE_VERSION)
                self.assertIn("selected_rule", row["evidence"])
                self.assertEqual(row["evidence"]["selected_rule"], "M-001")
                self.assertIn("counterpart_canonical_id", row["evidence"])
        finally:
            db.close()

    def test_ambiguity_evidence_preserves_candidate_set(self) -> None:
        db = LedgerDatabase()
        try:
            ingestion = RawIngestion(db)
            register_sources(ingestion)
            batch_a, _ = seed_records(db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                                      batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
            batch_b, _ = seed_records(db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                                      batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
            run_standard_pipeline(db, [batch_a, batch_b], reconcile_invalid=True)
            for row in _all_reconciliation_rows(db):
                if row["outcome"] != "AMBIGUOUS":
                    continue
                evaluation = row["evidence"]["evaluation"]
                self.assertEqual(evaluation["selected_rule"], "M-002")
                self.assertGreaterEqual(len(evaluation["selected_counterparts"]), 2)
        finally:
            db.close()


class ResolutionProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = run_portfolio()
        self.db = LedgerDatabase()
        ingestion = RawIngestion(self.db)
        register_sources(ingestion)
        batch_a, _ = seed_records(self.db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                                  batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
        batch_b, _ = seed_records(self.db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                                  batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
        run_standard_pipeline(self.db, [batch_a, batch_b], reconcile_invalid=True)

    def tearDown(self) -> None:
        self.db.close()

    def test_discrepancy_state_machine_matches_workflow(self) -> None:
        states = {entry["record_id"]: entry["state"] for entry in _discrepancy_table(self.db)}
        # The run_portfolio resolution workflow is applied in this test itself.
        from product_proof.runner import _apply_resolutions, ProofRecorder
        _apply_resolutions(self.db, ProofRecorder("test"))
        states = {entry["record_id"]: entry["state"] for entry in _discrepancy_table(self.db)}
        self.assertEqual(states, {"A004": "RESOLVED", "A006": "RESOLVED", "A007": "DEFERRED",
                                  "B994": "REJECTED", "B995": "OPEN"})

    def test_resolved_reconciliations_supersede_with_version_two(self) -> None:
        from product_proof.runner import _apply_resolutions, ProofRecorder
        _apply_resolutions(self.db, ProofRecorder("test"))
        resolved = [row for row in _all_reconciliation_rows(self.db) if row["state"] == "RESOLVED"]
        self.assertEqual(len(resolved), 2)
        for row in resolved:
            self.assertEqual(row["reconciliation_version"], 2)
            self.assertEqual(row["supersedes_reconciliation_id"] is not None, True)
            self.assertEqual(row["resolution_id"] is not None, True)
        # Superseded v1 rows keep their original outcome.
        superseded = [row for row in _all_reconciliation_rows(self.db)
                      if row["supersedes_reconciliation_id"] is None and row["outcome"] in {"AMBIGUOUS", "MISMATCHED"}]
        self.assertEqual(len(superseded), 5)


class ApiReportingProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = LedgerDatabase()
        ingestion = RawIngestion(self.db)
        register_sources(ingestion)
        self.batch_a, _ = seed_records(self.db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                                       batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
        self.batch_b, _ = seed_records(self.db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                                       batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
        run_standard_pipeline(self.db, [self.batch_a, self.batch_b], reconcile_invalid=True)
        self.api = LedgerAPI(self.db, token_verifier=_token_verifier())
        self.operator = {"Authorization": "Bearer operator"}
        self.reader_a = {"Authorization": "Bearer reader-a"}

    def tearDown(self) -> None:
        self.db.close()

    def test_report_agrees_with_authoritative_state(self) -> None:
        status, body = self.api.handle("GET", "/reports", headers=self.operator)
        self.assertEqual(status, 200)
        authoritative = outcome_count_values(pipeline_decisions(self.db))
        self.assertEqual(body["data"]["outcomes"], authoritative)
        self.assertEqual(body["data"]["reconciliation_count"], len(pipeline_decisions(self.db)))

    def test_export_contains_no_raw_payload_values(self) -> None:
        status, body = self.api.handle("GET", "/export", headers=self.operator)
        self.assertEqual(status, 200)
        text = json.dumps(body)
        leaked = [value for value in _raw_payload_values(self.db) if value and value in text]
        self.assertEqual(leaked, [])

    def test_source_isolation_and_roles(self) -> None:
        status, _ = self.api.handle("GET", "/reports", {"batch_id": self.batch_b}, self.reader_a)
        self.assertEqual(status, 403)
        status, body = self.api.handle("GET", "/reconciliations", headers=self.reader_a)
        self.assertEqual(status, 200)
        allowed = [row for row in _all_reconciliation_rows(self.db) if row["batch_id"] == self.batch_a]
        self.assertEqual(len(body["data"]), len(allowed))
        entry = _discrepancy_table(self.db)[0]
        status, _ = self.api.handle("POST", f"/discrepancies/{entry['discrepancy_id']}/resolve",
                                    {"resolution_type": "MANUAL_APPROVED", "reason": "x"}, self.reader_a)
        self.assertEqual(status, 403)
        status, _ = self.api.handle("GET", "/reports")
        self.assertEqual(status, 401)


class ReplayAndHistoryProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = LedgerDatabase()
        ingestion = RawIngestion(self.db)
        register_sources(ingestion)
        self.batch_a, _ = seed_records(self.db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                                       batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
        self.batch_b, _ = seed_records(self.db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                                       batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
        run_standard_pipeline(self.db, [self.batch_a, self.batch_b], reconcile_invalid=True)

    def tearDown(self) -> None:
        self.db.close()

    def test_pipeline_replay_is_idempotent_without_duplicates(self) -> None:
        before = {table: row_count(self.db, table) for table in
                  ("raw_records", "canonical_transactions", "match_candidates", "reconciliations")}
        run_standard_pipeline(self.db, [self.batch_a, self.batch_b], reconcile_invalid=True)
        run_standard_pipeline(self.db, [self.batch_a, self.batch_b], reconcile_invalid=True)
        after = {table: row_count(self.db, table) for table in before}
        self.assertEqual(before, after)

    def test_submission_duplicate_does_not_create_raw_row(self) -> None:
        ingestion = RawIngestion(self.db)
        raw_before = row_count(self.db, "raw_records")
        result = ingestion.ingest(self.batch_a, dict(dataset.PORTFOLIO_A["A001"]),
                                  idempotency_key="pf-a:A001", accepted_at=dataset.now())
        self.assertTrue(result.duplicate_submission)
        self.assertEqual(row_count(self.db, "raw_records"), raw_before)

    def test_late_arrival_preserves_prior_decisions(self) -> None:
        prior = _all_reconciliation_rows(self.db)
        a003_unmatched = [row for row in prior if "A003" in _row_names(self.db, row)]
        self.assertEqual(len(a003_unmatched), 1)
        late_batch, _ = seed_records(self.db, "source-b", "source_b.v1", dataset.LATE_B,
                                     batch_id="pf-batch-b-late", external_batch_id="pf-ext-b-late",
                                     idempotency_prefix="pf-late")
        validate_batches(self.db, [late_batch])
        normalize_raw_ids(self.db, [row.raw_record_id for row in self.db.raw_records.list_for_batch(late_batch)])
        verify_identities(self.db)
        generate_candidates(self.db)
        evaluate_matching(self.db)
        after = _all_reconciliation_rows(self.db)
        for row in prior:
            self.assertIn(row, after)
        a003_rows = [row for row in after if "A003" in _row_names(self.db, row)]
        self.assertEqual(len(a003_rows), 2)
        self.assertIn("MATCHED", {row["outcome"] for row in a003_rows})
        self.assertEqual(row_count(self.db, "reconciliations"), len(prior) + 1)
        # Architecture section 28 / D-007: the late arrival creates a linked
        # superseding version and never reopens or overwrites the original.
        original = a003_unmatched[0]
        superseding = [row for row in a003_rows if row["outcome"] == "MATCHED"]
        self.assertEqual(len(superseding), 1)
        self.assertEqual(superseding[0]["reconciliation_version"], 2)
        self.assertEqual(superseding[0]["supersedes_reconciliation_id"], original["reconciliation_id"])
        self.assertEqual(superseding[0]["state"], "MATCHED")
        current_ids = {row.reconciliation_id for row in self.db.reconciliations.list_current()}
        self.assertIn(superseding[0]["reconciliation_id"], current_ids)
        self.assertNotIn(original["reconciliation_id"], current_ids)
        # Re-evaluating the same authoritative state adds no version.
        evaluate_matching(self.db)
        self.assertEqual(row_count(self.db, "reconciliations"), len(prior) + 1)

    def test_raw_history_is_immutable(self) -> None:
        row = self.db.connection.execute(
            "SELECT raw_record_id, payload_json FROM raw_records ORDER BY raw_record_id LIMIT 1").fetchone()
        with self.assertRaises(Exception):
            self.db.connection.execute("UPDATE raw_records SET payload_json = '{}' WHERE raw_record_id = ?",
                                       (row["raw_record_id"],))
            self.db.connection.commit()
        self.db.connection.rollback()
        self.assertEqual(self.db.connection.execute(
            "SELECT payload_json FROM raw_records WHERE raw_record_id = ?", (row["raw_record_id"],)).fetchone()[0],
            row["payload_json"])


class ScenarioProofTests(unittest.TestCase):
    def test_correction_preserves_immutable_history(self) -> None:
        result = run_correction()
        self.assertTrue(_all_checks_pass(result), [c for c in result["checks"] if not c["passed"]])
        db = LedgerDatabase()
        try:
            ingestion = RawIngestion(db)
            register_sources(ingestion)
            batch_a, _ = seed_records(db, "source-a", "source_a.v1", dataset.CORRECTION_A,
                                      batch_id="corr-batch-a", external_batch_id="corr-ext-a", idempotency_prefix="corr-a")
            batch_b, _ = seed_records(db, "source-b", "source_b.v1", dataset.CORRECTION_B,
                                      batch_id="corr-batch-b", external_batch_id="corr-ext-b", idempotency_prefix="corr-b")
            run_standard_pipeline(db, [batch_a, batch_b])
            original = db.raw_records.find_by_source_record("source-a", "source_a.v1", "P-1")[0]
            corrected = ingestion.ingest(batch_a, dict(dataset.CORRECTED_P1_PAYLOAD),
                                         idempotency_key="corr-a:P-1:corrected", accepted_at=dataset.now())
            corrected_raw = db.raw_records.get(corrected.raw_record_id)  # type: ignore[arg-type]
            self.assertIsNotNone(corrected_raw)
            self.assertEqual(corrected_raw.supersedes_raw_record_id, original.raw_record_id)  # type: ignore[union-attr]
            self.assertEqual(row_count(db, "raw_records"), 3)
            self.assertEqual(row_count(db, "canonical_transactions"), 2)
        finally:
            db.close()

    def test_restart_reopen_reproduces_state(self) -> None:
        result = run_restart()
        self.assertTrue(_all_checks_pass(result), [c for c in result["checks"] if not c["passed"]])

    def test_telemetry_is_structured_and_redacted(self) -> None:
        result = run_telemetry()
        self.assertTrue(_all_checks_pass(result), [c for c in result["checks"] if not c["passed"]])

    def test_full_proof_is_deterministic_and_reproducible(self) -> None:
        first = run_full_proof()
        second = run_full_proof()
        self.assertTrue(_all_checks_pass(first))
        self.assertTrue(_all_checks_pass(second))
        self.assertEqual(first["signature"], second["signature"])
        self.assertEqual(first["manifest_sha256"], dataset.manifest_sha256())


if __name__ == "__main__":
    unittest.main()
