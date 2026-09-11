# Layer 13 Performance Evidence

Run the reproducible benchmark from the repository root:

```sh
PYTHONPATH=src python3 benchmarks/run_performance.py
```

The runner uses the real SQLite-backed LEDGER services and writes
`evidence/performance-baseline.json`. It creates paired `source_a.v1` and
`source_b.v1` records with deterministic IDs, dates, amounts, currencies, and
references. Every eighth pair has a direction mismatch so reconciliation and
manual resolution are exercised. Dataset sizes are 32, 64, and 128 records per
source (64, 128, and 256 total records).

Each size has one warm-up and five measured iterations. The harness records
stage latency for ingestion, validation, normalization, identity, indexed
candidate generation, matching/reconciliation, and resolution; median and
nearest-rank p95 latency; record throughput; peak `tracemalloc` memory; the
candidate-set distribution; machine/runtime/SQLite metadata; and a SHA-256
correctness signature. The signature must be identical across measured
iterations.

Candidate scaling is checked against the architecture's indexed candidate
contract. The fixture gives each pair one legitimate counterpart, so candidate
count is linear in the number of pairs while the all-pairs comparison is
quadratic. The runner fails if candidate count exceeds five times the pair
count, and records the candidate/all-pairs ratio as evidence. This is a
candidate-path check, not an unsupported runtime SLO.

The checked-in JSON is a baseline from the environment where the benchmark was
last run. These stage numbers are in-process and memory-backed, so they measure
the pipeline's algorithmic cost, not durable write cost. The numerical SLOs for
the single-host reference environment were resolved in Architecture D-009
against the Epic 8 staging rehearsal (see `docs/staging.md`); rerun the harness
on a target machine before making capacity claims about that machine.
