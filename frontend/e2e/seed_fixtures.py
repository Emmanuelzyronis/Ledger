"""Deterministic fixtures for the dashboard end-to-end suite.

Populates a real SQLite database with the Layer 15 portfolio fixtures using the
repository's own pipeline driver, then writes a manifest of identifiers and
expected counts for the Playwright suite.

Pipeline execution (validation through reconciliation) is not an HTTP operation
in v1.0: Architecture section 37 lists no processing endpoint, and section 2157
makes resolution the only API mutation. The seed therefore drives the same real
services the product-proof runner does instead of inventing an endpoint.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from ledger.ingestion import RawIngestion  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from ledger.reporting import ReportingService  # noqa: E402
from product_proof import dataset  # noqa: E402
from product_proof.pipeline import register_sources, run_standard_pipeline, seed_records  # noqa: E402

RESOLVABLE = {"AMBIGUOUS", "MISMATCHED"}


def main() -> int:
    database_path, manifest_path = sys.argv[1], sys.argv[2]
    database = LedgerDatabase(database_path)
    try:
        ingestion = RawIngestion(database)
        register_sources(ingestion)
        batch_a, _ = seed_records(
            database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
            batch_id="e2e-batch-a", external_batch_id="e2e-ext-a", idempotency_prefix="e2e-a")
        batch_b, _ = seed_records(
            database, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
            batch_id="e2e-batch-b", external_batch_id="e2e-ext-b", idempotency_prefix="e2e-b")
        run_standard_pipeline(database, [batch_a, batch_b], reconcile_invalid=True)

        rows = database.connection.execute(
            "SELECT d.discrepancy_id, d.reconciliation_id, d.state, d.reason, r.outcome, r.batch_id "
            "FROM discrepancies d JOIN reconciliations r "
            "ON r.reconciliation_id = d.reconciliation_id ORDER BY d.discrepancy_id").fetchall()
        discrepancies = [dict(row) for row in rows]
        targets = [row for row in discrepancies if row["state"] == "OPEN" and row["outcome"] in RESOLVABLE]
        if not targets:
            raise SystemExit("no open resolvable discrepancy was produced by the fixtures")

        report = ReportingService(database).report()
        manifest = {
            "database_path": database_path,
            "batches": {"a": batch_a, "b": batch_b},
            "discrepancies": discrepancies,
            "resolution_target": targets[0],
            "report": {
                "reconciliation_count": report["reconciliation_count"],
                "current_reconciliation_count": report["current_reconciliation_count"],
                "outcomes": report["outcomes"],
                "current_outcomes": report["current_outcomes"],
                "discrepancy_count": report["discrepancy_count"],
            },
        }
        Path(manifest_path).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({
            "batches": [batch_a, batch_b],
            "discrepancies": len(discrepancies),
            "resolution_target": targets[0]["discrepancy_id"],
            "reconciliation_count": report["reconciliation_count"],
        }, sort_keys=True))
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
