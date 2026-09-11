# LEDGER

LEDGER is a deterministic transaction reconciliation engine. The repository is being built one controlled implementation layer at a time; see `Architecture.md` and `prompts/README.md` for the authoritative contracts and sequence.

## Current implementation

The repository contains implemented and tested Layers 1-15: Foundation, the infrastructure-independent Domain Model, SQLite Persistence, Raw Ingestion, Validation, Normalization, Identity, Candidate Generation, Matching, Reconciliation, Resolution + Audit, API + Reporting, Performance, Failure Verification, and Product Proof. Persistence includes immutable historical records, correction/version links, replay association, and atomic state-plus-audit writes. Resolution applies authorized deterministic decisions with immutable lineage and append-only audit history. API and reporting expose authenticated, scoped business operations and rebuildable read-only projections.

Layer 15 product proof is covered by `tests/test_product_proof.py` and the standalone runner
`PYTHONPATH=src python3 product_proof/run_product_proof.py`. The runner drives the real
SQLite-backed services over deterministic fixtures, proves the full mission flow and all seven
reconciliation outcomes, and writes reproducible evidence to `evidence/product-proof.json`;
methodology, scenarios, observed outcomes, and limitations are documented in
`docs/product-proof.md`.

Layer 14 failure verification is covered by `tests/test_failure_verification.py`; the
scenarios, methodology, observed behavior, and limitations are documented in
`docs/failure-verification.md`.

Layer 13 performance benchmarking is available via `PYTHONPATH=src python3 benchmarks/run_performance.py`.
The runner measures the real SQLite-backed pipeline across ingestion, validation, normalization, identity,
indexed candidate generation, matching/reconciliation, and resolution. It records deterministic correctness
signatures, stage latency/throughput, peak memory, candidate distributions, and environment metadata in
`evidence/performance-baseline.json`; methodology is documented in `docs/performance.md`.

Current verification: 114 tests pass; `make check`, `python3 -m compileall src tests benchmarks product_proof`, and `git diff --check` also pass.

Run the repository checks with:

```sh
make check
```

Secrets are supplied through the runtime environment or a secret manager. Do not commit `.env` files or credentials.
