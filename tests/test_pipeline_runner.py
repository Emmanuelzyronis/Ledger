"""EMM-110 operator pipeline runner: selection, idempotency, partial failure.

The tests drive the real runner over a real SQLite database seeded with the
Layer 15 portfolio fixtures, and assert the properties the runner is published
to guarantee: only selected batches change, counters are authoritative and
reconcile, a repeated run writes nothing new, a completed batch is never
reopened, and a stage failure becomes an explicit terminal state with a
non-zero exit code instead of a silently partial result.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ledger import pipeline  # noqa: E402
from ledger.domain import BatchState  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from product_proof import dataset  # noqa: E402
from product_proof.pipeline import register_sources, seed_records  # noqa: E402


COUNTER_IDENTITY = (
    "processed_count",
    "matched_count",
    "mismatched_count",
    "unmatched_count",
    "ambiguous_count",
    "duplicate_count",
    "invalid_count",
)


def seed(database_path: str) -> tuple[str, str]:
    database = LedgerDatabase(database_path)
    try:
        ingestion = register_sources_and_ingest(database)
        return ingestion
    finally:
        database.close()


def register_sources_and_ingest(database: LedgerDatabase) -> tuple[str, str]:
    register_sources(__import__("ledger.ingestion", fromlist=["RawIngestion"]).RawIngestion(database))
    from ledger.ingestion import RawIngestion

    ingestion = RawIngestion(database)
    register_sources(ingestion)
    batch_a, _ = seed_records(database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                              batch_id="batch-a", external_batch_id="ext-a", idempotency_prefix="a")
    batch_b, _ = seed_records(database, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
                              batch_id="batch-b", external_batch_id="ext-b", idempotency_prefix="b")
    return batch_a, batch_b


def table_counts(database: LedgerDatabase) -> dict[str, int]:
    return {
        table: int(database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in ("raw_records", "canonical_transactions", "reconciliations", "discrepancies",
                      "audit_events", "processing_attempts")
    }


class PipelineRunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="ledger-pipeline-")
        self.database_path = str(Path(self.directory) / "ledger.sqlite3")
        self.batch_a, self.batch_b = seed(self.database_path)
        self.database = LedgerDatabase(self.database_path)
        self.addCleanup(self.database.close)
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def test_selection_by_state_excludes_completed_and_rejected(self):
        selected = pipeline.select_batches(self.database)
        self.assertEqual(selected, sorted([self.batch_a, self.batch_b]))
        self.assertNotIn(BatchState.COMPLETED, pipeline.PENDING_STATES)
        self.assertNotIn(BatchState.REJECTED, pipeline.PENDING_STATES)

    def test_runner_completes_batches_and_reconciles_counters(self):
        runs = pipeline.process_batches(self.database, [self.batch_a, self.batch_b],
                                        evaluated_at=dataset.NOW)
        self.assertEqual([run.status for run in runs], ["processed", "processed"])
        for run in runs:
            self.assertEqual(run.state, "COMPLETED")
            counters = run.counters
            self.assertEqual(counters["received_count"],
                             counters["accepted_count"] + counters["rejected_input_count"])
            self.assertEqual(
                counters["processed_count"],
                sum(counters[name] for name in COUNTER_IDENTITY[1:]),
            )
            self.assertEqual(counters["failed_count"], 0)
            # Every accepted record reached a terminal outcome.
            self.assertEqual(counters["processed_count"],
                             counters["accepted_count"] - counters["failed_count"])

    def test_runner_reproduces_the_expected_portfolio_outcomes(self):
        pipeline.process_batches(self.database, [self.batch_a, self.batch_b], evaluated_at=dataset.NOW)
        from ledger.pipeline import _record_outcomes  # noqa: PLC2701 - internal mapping under test

        mapped = _record_outcomes(self.database, [self.batch_a, self.batch_b])
        by_source: dict[str, str] = {}
        for raw_id, entry in mapped.items():
            raw = self.database.raw_records.get(raw_id)
            by_source[raw.source_record_id] = entry["outcome"]
        for record_id, expected in dataset.EXPECTED_PORTFOLIO_OUTCOMES.items():
            with self.subTest(record=record_id):
                self.assertEqual(by_source.get(record_id), expected)

    def test_rerun_is_idempotent_and_writes_nothing_new(self):
        first = pipeline.process_batches(self.database, [self.batch_a, self.batch_b], evaluated_at=dataset.NOW)
        before = table_counts(self.database)
        second = pipeline.process_batches(self.database, [self.batch_a, self.batch_b], evaluated_at=dataset.NOW)
        after = table_counts(self.database)
        # Authoritative effects are identical; only the attempt rows of the
        # second (skipped) run differ.
        self.assertEqual(before, after)
        self.assertEqual([run.status for run in second], ["skipped", "skipped"])
        for original, repeated in zip(first, second):
            self.assertEqual(original.state, repeated.state)
            self.assertEqual(original.counters, repeated.counters)
            self.assertEqual(repeated.outcomes, {})
            self.assertEqual(original.outcomes, first[first.index(original)].outcomes)
        batch = self.database.batches.get(self.batch_a)
        self.assertEqual(batch.state, BatchState.COMPLETED)
        first_outcomes = {run.batch_id: run.outcomes for run in first}
        self.assertTrue(all(first_outcomes.values()), first_outcomes)

    def test_completed_batch_is_never_reopened_by_state_selection(self):
        pipeline.process_batches(self.database, [self.batch_a, self.batch_b], evaluated_at=dataset.NOW)
        self.assertEqual(pipeline.select_batches(self.database), [])
        _, runtime = _invoke(["process", "--database", self.database_path])
        self.assertEqual(runtime, 0)
        self.assertEqual(json.loads(_stdout)["selected"], 0)

    def test_stage_failure_becomes_an_explicit_terminal_state(self):
        original = pipeline._run_stages

        def explode(*args, **kwargs):
            raise RuntimeError("stage exploded")

        pipeline._run_stages = explode
        self.addCleanup(setattr, pipeline, "_run_stages", original)
        runs = pipeline.process_batches(self.database, [self.batch_a])
        self.assertEqual(runs[0].status, "failed")
        self.assertIn("stage exploded", runs[0].error)
        attempt = self.database.processing_attempts.get(runs[0].attempt_id)
        self.assertEqual(attempt.state.value, "FAILED")
        # Validation never completed, so the batch must NOT claim a later state:
        # it stays retryable and the failure lives on the attempt row.
        self.assertEqual(runs[0].state, "RECEIVED")
        self.assertEqual(self.database.batches.get(self.batch_a).state, BatchState.RECEIVED)
        self.assertIn(self.batch_a, pipeline.select_batches(self.database))

    def test_failure_after_validation_marks_the_batch_failed_and_retryable(self):
        from ledger import pipeline as runner

        original = runner.MatchingService

        class BrokenMatching:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("matching exploded")

        runner.MatchingService = BrokenMatching
        try:
            runs = runner.process_batches(self.database, [self.batch_a])
        finally:
            runner.MatchingService = original
        self.assertEqual(runs[0].status, "failed")
        self.assertEqual(runs[0].state, "FAILED")
        self.assertEqual(self.database.batches.get(self.batch_a).state, BatchState.FAILED)
        # FAILED is a retryable pending state, so the operator can re-run it.
        self.assertIn(self.batch_a, pipeline.select_batches(self.database))
        retry = runner.process_batches(self.database, [self.batch_a], evaluated_at=dataset.NOW)
        self.assertEqual(retry[0].state, "COMPLETED")

    def test_cli_returns_two_on_processing_failure(self):
        original = pipeline._run_stages
        pipeline._run_stages = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        self.addCleanup(setattr, pipeline, "_run_stages", original)
        _, status = _invoke(["process", "--database", self.database_path, "--batch", self.batch_a])
        self.assertEqual(status, 2)
        payload = json.loads(_stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["runs"][0]["status"], "failed")

    def test_cli_rejects_unknown_batch_and_mixed_selection(self):
        _, status = _invoke(["process", "--database", self.database_path, "--batch", "nope"])
        self.assertEqual(status, 1)
        _, status = _invoke(["process", "--database", self.database_path,
                             "--batch", self.batch_a, "--state", "RECEIVED"])
        self.assertEqual(status, 1)

    def test_cli_list_and_process_round_trip(self):
        _, status = _invoke(["list", "--database", self.database_path])
        self.assertEqual(status, 0)
        listed = json.loads(_stdout)
        self.assertEqual(listed["count"], 2)
        _, status = _invoke(["process", "--database", self.database_path,
                             "--state", "RECEIVED"])
        self.assertEqual(status, 0)
        payload = json.loads(_stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual([run["state"] for run in payload["runs"]], ["COMPLETED", "COMPLETED"])
        _, status = _invoke(["list", "--database", self.database_path])
        self.assertEqual(json.loads(_stdout)["count"], 0)


_stdout = ""


def _invoke(argv: list[str]) -> tuple[str, int]:
    global _stdout
    buffer = io.StringIO()
    errors = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(errors):
        status = pipeline.main(argv)
    _stdout = buffer.getvalue()
    return _stdout, status


if __name__ == "__main__":
    unittest.main()
