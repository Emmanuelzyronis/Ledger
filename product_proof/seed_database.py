"""Populate a real SQLite database with the Layer 15 portfolio fixtures.

Used by the Epic 5 database-operations drill so backup/restore evidence is
produced against a representative database with real authoritative state,
immutable history, and audit lineage rather than an empty file.

Usage: PYTHONPATH=src python3 product_proof/seed_database.py PATH
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from ledger.ingestion import RawIngestion  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from ledger.reporting import ReportingService  # noqa: E402

from product_proof import dataset  # noqa: E402
from product_proof.pipeline import register_sources, run_standard_pipeline, seed_records  # noqa: E402


def main() -> int:
    path = sys.argv[1]
    database = LedgerDatabase(path)
    try:
        ingestion = RawIngestion(database)
        register_sources(ingestion)
        batch_a, _ = seed_records(
            database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
            batch_id="ops-batch-a", external_batch_id="ops-ext-a", idempotency_prefix="ops-a")
        batch_b, _ = seed_records(
            database, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
            batch_id="ops-batch-b", external_batch_id="ops-ext-b", idempotency_prefix="ops-b")
        run_standard_pipeline(database, [batch_a, batch_b], reconcile_invalid=True)
        rows = {table: database.connection.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("raw_records", "canonical_transactions", "reconciliations",
                          "discrepancies", "audit_events")}
        print(json.dumps({"database": path, "rows": rows,
                          "report": ReportingService(database).report()["outcomes"]},
                         indent=2, sort_keys=True))
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
