"""Run deterministic Layer 13 benchmarks for the real LEDGER pipeline.

Usage: PYTHONPATH=src python3 benchmarks/run_performance.py
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ledger.candidates import CandidateGenerationService
from ledger.domain import ResolutionType
from ledger.identity import IdentityService
from ledger.ingestion import RawIngestion
from ledger.matching import MatchingService
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.resolution import ResolutionService
from ledger.validation import ValidationService


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "performance-baseline.json"
NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
WARMUPS = 1
ITERATIONS = 5
PAIR_COUNTS = (32, 64, 128)


def _payloads(count: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    left, right = [], []
    for index in range(count):
        amount = f"{100 + index}.0000"
        day = (NOW + timedelta(days=index % 5)).date().isoformat()
        reference = f"REF-{index:06d}"
        left.append({"record_id": f"A-{index:06d}", "occurred_at": day, "amount": amount,
                     "currency": "USD", "direction": "CREDIT", "account_reference": "acct-a",
                     "transaction_reference": reference, "description": f"Payment {index}",
                     "transaction_type": "SALE"})
        right.append({"id": f"B-{index:06d}", "posted": day, "value": amount,
                      "ccy": "USD", "side": "DEBIT" if index % 8 == 0 else "CREDIT",
                      "account_ref": "acct-b", "reference": reference, "memo": f"Payment {index}",
                      "type": "SALE"})
    return left, right


def _setup(count: int) -> tuple[LedgerDatabase, dict[str, Any]]:
    db = LedgerDatabase()
    ingestion = RawIngestion(db)
    ingestion.register_source("source-a", "Source A", ["source_a.v1"])
    ingestion.register_source("source-b", "Source B", ["source_b.v1"])
    batch_a = ingestion.create_batch("source-a", f"bench-a-{count}", "source_a.v1", batch_id=f"batch-a-{count}", received_at=NOW)
    batch_b = ingestion.create_batch("source-b", f"bench-b-{count}", "source_b.v1", batch_id=f"batch-b-{count}", received_at=NOW)
    payload_a, payload_b = _payloads(count)
    return db, {"ingestion": ingestion, "batch_a": batch_a.batch_id, "batch_b": batch_b.batch_id,
                "payload_a": payload_a, "payload_b": payload_b}


def _pipeline(count: int) -> tuple[dict[str, float], dict[str, Any], str, int]:
    db, ctx = _setup(count)
    timings: dict[str, float] = {}
    try:
        ingestion: RawIngestion = ctx["ingestion"]
        started = time.perf_counter()
        ingestion.ingest_batch(ctx["batch_a"], ctx["payload_a"], idempotency_prefix="a")
        ingestion.ingest_batch(ctx["batch_b"], ctx["payload_b"], idempotency_prefix="b")
        timings["ingestion"] = time.perf_counter() - started

        validation = ValidationService(db)
        started = time.perf_counter()
        validation.validate_batch(ctx["batch_a"])
        validation.validate_batch(ctx["batch_b"])
        timings["validation"] = time.perf_counter() - started

        normalization = NormalizationService(db)
        raw_ids = [row.raw_record_id for row in db.raw_records.list_for_batch(ctx["batch_a"])]
        raw_ids += [row.raw_record_id for row in db.raw_records.list_for_batch(ctx["batch_b"])]
        started = time.perf_counter()
        canonical = [normalization.normalize_record(raw_id) for raw_id in raw_ids]
        canonical = [item for item in canonical if item is not None]
        timings["normalization"] = time.perf_counter() - started

        identities = IdentityService(db)
        started = time.perf_counter()
        identity_values = [identities.identify(item) for item in canonical]
        timings["identity"] = time.perf_counter() - started

        candidates = CandidateGenerationService(db)
        started = time.perf_counter()
        candidate_values = candidates.generate_all()
        timings["candidate_generation"] = time.perf_counter() - started

        matching = MatchingService(db)
        reconciliation_elapsed = 0.0
        original_persist = matching.reconciliation.persist_decision

        def timed_persist(*args: Any, **kwargs: Any) -> Any:
            nonlocal reconciliation_elapsed
            started = time.perf_counter()
            result = original_persist(*args, **kwargs)
            reconciliation_elapsed += time.perf_counter() - started
            return result

        matching.reconciliation.persist_decision = timed_persist  # type: ignore[method-assign]
        started = time.perf_counter()
        decisions = matching.evaluate(candidate_values, evaluated_at=NOW)
        total_matching = time.perf_counter() - started
        timings["reconciliation"] = reconciliation_elapsed
        timings["matching"] = max(0.0, total_matching - reconciliation_elapsed)

        resolution = ResolutionService(db)
        discrepancy_rows = db.connection.execute(
            "SELECT discrepancy_id FROM discrepancies ORDER BY discrepancy_id"
        ).fetchall()
        discrepancies = [db.discrepancies.get(row["discrepancy_id"]) for row in discrepancy_rows]
        discrepancies = [item for item in discrepancies if item is not None]
        started = time.perf_counter()
        if discrepancies:
            resolution.resolve(discrepancies[0].discrepancy_id, ResolutionType.MANUAL_APPROVED,
                               actor="reconciliation_operator", reason="benchmark evidence", created_at=NOW)
        timings["resolution"] = time.perf_counter() - started

        outcomes = sorted((decision.reconciliation.reconciliation_id, decision.outcome.value) for decision in decisions)
        candidate_sizes = [sum(item.canonical_id in (candidate.source_a_canonical_id, candidate.source_b_canonical_id)
                               for candidate in candidate_values) for item in canonical]
        signature_data = {"identities": [item.canonical_identity for item in identity_values],
                          "candidates": [(item.source_a_canonical_id, item.source_b_canonical_id, item.eligible_rule_ids)
                                         for item in candidate_values], "outcomes": outcomes}
        signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True, default=str).encode()).hexdigest()
        return timings, {"records": len(canonical), "candidate_count": len(candidate_values),
                         "candidate_sizes": candidate_sizes, "discrepancies": len(discrepancies),
                         "matched_decisions": len(decisions)}, signature, len(discrepancies)
    finally:
        db.close()


def _stats(samples: list[float], records: int) -> dict[str, float]:
    ordered = sorted(samples)
    return {"median_seconds": statistics.median(samples),
            "p95_seconds": ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))],
            "throughput_records_per_second": records / statistics.median(samples)}


def _run_size(count: int) -> dict[str, Any]:
    for _ in range(WARMUPS):
        _pipeline(count)
    samples: dict[str, list[float]] = {}
    peak_memory = 0
    signatures: list[str] = []
    details: dict[str, Any] = {}
    for _ in range(ITERATIONS):
        tracemalloc.start()
        timings, details, signature, _ = _pipeline(count)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_memory = max(peak_memory, peak)
        signatures.append(signature)
        for stage, elapsed in timings.items():
            samples.setdefault(stage, []).append(elapsed)
    if len(set(signatures)) != 1:
        raise AssertionError("benchmark output is not deterministic")
    return {"records_per_source": count, "records_total": count * 2,
            "stages": {stage: _stats(values, count * 2) for stage, values in samples.items()},
            "peak_memory_bytes": peak_memory, "candidate_distribution": {
                "count": details["candidate_count"], "min": min(details["candidate_sizes"]),
                "median": statistics.median(details["candidate_sizes"]), "max": max(details["candidate_sizes"]),
                "all_pairs_comparison": count * count}, "correctness_signature": signatures[0],
            "resolution_discrepancies": details["discrepancies"]}


def main() -> None:
    results = {str(count): _run_size(count) for count in PAIR_COUNTS}
    scaling = []
    for count in PAIR_COUNTS:
        candidate_count = results[str(count)]["candidate_distribution"]["count"]
        if candidate_count > count * 5:
            raise AssertionError("candidate generation exceeded bounded candidate budget")
        scaling.append({"records_per_source": count, "candidate_count": candidate_count,
                        "all_pairs": count * count, "candidate_to_all_pairs_ratio": candidate_count / (count * count)})
    manifest = {"dataset": {"shape": "paired source_a.v1/source_b.v1 records; unique reference and amount/date keys; every 8th pair direction mismatch", "sizes": list(PAIR_COUNTS), "payload_sha256": hashlib.sha256(json.dumps(_payloads(max(PAIR_COUNTS)), sort_keys=True).encode()).hexdigest()},
                "method": {"warmup_iterations": WARMUPS, "measured_iterations": ITERATIONS, "clock": "time.perf_counter", "latency_statistic": "median and nearest-rank p95", "correctness": "stable SHA-256 signature of identities, candidates, and outcomes"},
                "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(), "sqlite": __import__("sqlite3").sqlite_version, "pid": os.getpid()},
                "results": results, "candidate_scaling": scaling}
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
