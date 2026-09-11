"""Epic 8 (EMM-84) staging rehearsal: representative dataset and load proof.

These tests drive the real staging proof against the real service transport.
They assert what the epic must guarantee: the scaled dataset is a faithful,
structure-preserving repetition of the proven Layer 15 portfolio (so a load
test measures scale, not new semantics); the rehearsal over real HTTP produces
the proven outcomes with no divergent decision; late arrival supersedes rather
than overwrites; recovery meets the approved D-014 objectives; the security
boundary holds; and the gate actually fails when a property is violated.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "staging"))

from run_staging_proof import evaluate_result, run as run_staging_proof  # noqa: E402

from product_proof import dataset as portfolio  # noqa: E402
from staging import dataset  # noqa: E402


def _is_amount(value: str) -> bool:
    try:
        Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return True


def _small_run() -> dict:
    return run_staging_proof(shards=2, clients=3, requests_per_client=4, long_batch_records=15)


class StagingDatasetTests(unittest.TestCase):
    def test_shards_are_disjoint_relabelings_of_the_proven_portfolio(self):
        shard_a, shard_b = dataset.shard_payloads(0)
        self.assertEqual(len(shard_a), len(portfolio.PORTFOLIO_A))
        self.assertEqual(len(shard_b), len(portfolio.PORTFOLIO_B))
        self.assertEqual(len(shard_a) + len(shard_b), dataset.RECORDS_PER_SHARD)
        self.assertEqual(set(shard_a), {f"{key}-S0" for key in portfolio.PORTFOLIO_A})
        self.assertEqual(set(shard_b), {f"{key}-S0" for key in portfolio.PORTFOLIO_B})

    def test_shards_cannot_collide_on_amount_or_reference(self):
        # Amounts are shifted by whole thousand-strides and references are
        # suffixed, so no candidate can pair a record from one shard with a
        # record from another. Amounts repeat *within* a shard by design (that
        # is what makes the AMBIGUOUS pair ambiguous).
        per_shard_amounts: list[set[str]] = []
        per_shard_references: list[set[str]] = []
        for shard in range(4):
            shard_a, shard_b = dataset.shard_payloads(shard)
            raw_amounts = {payload["amount"] for payload in shard_a.values()}
            raw_amounts |= {payload["value"] for payload in shard_b.values()}
            # The deliberately malformed INVALID record is never re-encoded, so
            # it is identical in every shard; it never reaches candidacy.
            amounts = {value for value in raw_amounts if _is_amount(value)}
            references = {payload["transaction_reference"] for payload in shard_a.values()
                          if payload.get("transaction_reference")}
            references |= {payload["reference"] for payload in shard_b.values() if payload.get("reference")}
            per_shard_amounts.append(amounts)
            per_shard_references.append(references)
        # Repetition inside a shard is deliberate (matching pairs share a
        # reference); the guarantee is that nothing repeats *between* shards.
        for index in range(len(per_shard_amounts)):
            for other in range(index + 1, len(per_shard_amounts)):
                self.assertFalse(per_shard_amounts[index] & per_shard_amounts[other],
                                 f"shards {index} and {other} share an amount")
                self.assertFalse(per_shard_references[index] & per_shard_references[other],
                                 f"shards {index} and {other} share a reference")

    def test_within_shard_amount_equality_is_preserved(self):
        # A004/B994/B995 are AMBIGUOUS because they share an amount; the shift
        # must keep that equality rather than break it.
        shard_a, shard_b = dataset.shard_payloads(2)
        self.assertEqual(shard_a["A001-S2"]["amount"], shard_a["A004-S2"]["amount"])
        self.assertEqual(shard_a["A004-S2"]["amount"], shard_b["B994-S2"]["value"])

    def test_shifting_preserves_the_equalities_the_outcomes_depend_on(self):
        for shard in range(3):
            shard_a, shard_b = dataset.shard_payloads(shard)
            # MATCHED pairs keep an equal reference; MISMATCHED pairs keep a
            # differing amount or direction.
            self.assertEqual(shard_a["A001-S%d" % shard]["transaction_reference"],
                             shard_b["B991-S%d" % shard]["reference"])
            self.assertEqual(shard_a["A002-S%d" % shard]["transaction_reference"],
                             shard_b["B992-S%d" % shard]["reference"])
            self.assertNotEqual(shard_a["A006-S%d" % shard]["amount"],
                                shard_b["B996-S%d" % shard]["value"])
            self.assertNotEqual(shard_a["A007-S%d" % shard]["direction"],
                                shard_b["B997-S%d" % shard]["side"])

    def test_malformed_values_stay_malformed(self):
        # A005 is the invalid record; shifting must not accidentally repair it.
        shard_a, _ = dataset.shard_payloads(1)
        self.assertEqual(shard_a["A005-S1"]["amount"], portfolio.PORTFOLIO_A["A005"]["amount"])

    def test_expected_outcomes_scale_linearly_with_shards(self):
        self.assertEqual(dataset.expected_records_a(3), len(portfolio.PORTFOLIO_A) * 3)
        self.assertEqual(dataset.expected_outcomes(3),
                         {outcome: count * 3 for outcome, count in dataset.EXPECTED_PER_SHARD.items()})
        self.assertEqual(set(dataset.EXPECTED_PER_SHARD),
                         set(portfolio.EXPECTED_PORTFOLIO_OUTCOMES.values()))


class StagingProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _small_run()

    def test_rehearsal_over_real_http_has_no_problems(self):
        self.assertEqual(evaluate_result(self.result), [], self.result)
        self.assertEqual(self.result["pipeline"]["outcome_mismatches"], 0)
        self.assertEqual(set(self.result["pipeline"]["states"].values()), {"COMPLETED"})

    def test_every_record_matches_the_proven_portfolio_outcome(self):
        expected = self.result["pipeline"]["expected_outcome_counts"]
        self.assertEqual(self.result["pipeline"]["outcome_counts"], expected)
        self.assertEqual(self.result["pipeline"]["records_checked"], 34)

    def test_long_batch_completes_with_explicit_counters(self):
        long_batch = self.result["pipeline"]["long_batch"]
        self.assertEqual(long_batch["state"], "COMPLETED")
        self.assertEqual(long_batch["counters"]["accepted_count"], 15)
        self.assertEqual(long_batch["counters"]["processed_count"], 15)
        self.assertEqual(long_batch["counters"]["unmatched_count"], 15)

    def test_late_arrival_supersedes_without_overwriting_history(self):
        late = self.result["late_arrival"]
        self.assertEqual(late["before"]["outcome"], "UNMATCHED_A")
        self.assertEqual(late["after"]["outcome"], "MATCHED")
        self.assertEqual(late["after"]["reconciliation_version"], late["before"]["reconciliation_version"] + 1)
        self.assertEqual(late["after"]["supersedes_reconciliation_id"], late["before"]["reconciliation_id"])
        self.assertTrue(late["prior_version_retrievable"])

    def test_security_boundary_holds_over_the_real_transport(self):
        security = self.result["security"]
        self.assertEqual(security["unauthenticated_read"], 401)
        self.assertEqual(security["invalid_token"], 401)
        self.assertIn(security["wrong_scope_batch"], (403, 404))
        self.assertEqual(security["operator_scoped_read"], 200)
        self.assertEqual(security["correlation_echo"]["X-Correlation-ID"], "staging-correlation-1")

    def test_recovery_and_observability_are_verified_under_load(self):
        self.assertTrue(self.result["recovery"]["ok"])
        self.assertTrue(self.result["recovery"]["objectives_met"])
        self.assertTrue(self.result["observability"]["metrics_scraped"])
        self.assertTrue(self.result["observability"]["metrics_bounded_labels"])
        self.assertEqual(self.result["load"]["errors"], 0)


class StagingGateTests(unittest.TestCase):
    """The gate must fail, not merely observe, when a property is violated."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _small_run()

    def _break(self, mutate) -> list[str]:
        broken = deepcopy(self.result)
        mutate(broken)
        return evaluate_result(broken)

    def test_gate_reports_outcome_divergence(self):
        self.assertTrue(self._break(lambda r: r["pipeline"].update(outcome_mismatches=1)))

    def test_gate_reports_incomplete_batch(self):
        def mutate(result: dict) -> None:
            result["pipeline"]["states"] = {"batch-x": "FAILED"}
        self.assertTrue(self._break(mutate))

    def test_gate_reports_load_errors(self):
        self.assertTrue(self._break(lambda r: r["load"].update(errors=1)))

    def test_gate_reports_metrics_leak(self):
        self.assertTrue(self._break(lambda r: r["observability"].update(metrics_bounded_labels=False)))

    def test_gate_reports_recovery_failure(self):
        self.assertTrue(self._break(lambda r: r["recovery"].update(objectives_met=False)))

    def test_gate_reports_lost_history(self):
        self.assertTrue(self._break(lambda r: r["late_arrival"].update(prior_version_retrievable=False)))

    def test_gate_reports_a_broken_security_boundary(self):
        self.assertTrue(self._break(lambda r: r["security"].update(unauthenticated_read=200)))
        self.assertTrue(self._break(lambda r: r["security"].update(invalid_token=200)))
        self.assertTrue(self._break(lambda r: r["security"].update(operator_scoped_read=403)))


if __name__ == "__main__":
    unittest.main()
