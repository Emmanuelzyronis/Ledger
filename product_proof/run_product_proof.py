"""Run the deterministic Layer 15 product-proof suite and write evidence.

Usage: PYTHONPATH=src python3 product_proof/run_product_proof.py

The suite drives the real SQLite-backed LEDGER services over the fixed fixtures
in ``product_proof.dataset`` and writes ``evidence/product-proof.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_proof.runner import run_full_proof, write_evidence  # noqa: E402


def main() -> int:
    try:
        results = run_full_proof()
    except AssertionError as exc:
        print(f"PRODUCT PROOF FAILED: {exc}", file=sys.stderr)
        return 1
    target = write_evidence(results)
    checks = results["checks"]
    print(json.dumps({
        "status": "passed",
        "scenarios": sorted(results["scenarios"]),
        "checks_passed": sum(1 for check in checks if check["passed"]),
        "checks_total": len(checks),
        "signature": results["signature"],
        "evidence_file": str(target),
    }, indent=2, sort_keys=True))
    print("\nLEDGER CORE PRODUCT PROOF COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
