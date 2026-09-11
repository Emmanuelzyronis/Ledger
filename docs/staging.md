# Epic 8 — Staging Rehearsal and Representative Load

Run the reproducible rehearsal from the repository root:

```sh
PYTHONPATH=src python3 staging/run_staging_proof.py
```

It writes `evidence/staging-proof.json` and exits non-zero if any checked
property fails. `make staging-proof` runs the same command.

## What this is, and what it is not

This is a **staged rehearsal on one host over the real transport**: the same
service entrypoint (`ledger.__main__.serve`), the same HMAC bearer-token
verifier, the same SQLite authority, the same operator runner
(`ledger.pipeline`), the same metrics scrape, and the same recovery drill that
run in production. Nothing is stubbed and no in-process shortcut replaces an
HTTP call for the parts under test.

It is **not** a hosted multi-host environment. There is one process, one
database file, one filesystem, and no network latency between tiers. Capacity
claims, failure-domain claims, and orchestration claims therefore cannot be
made from this evidence. What it does establish is that the process model,
dataset semantics, security boundary, recovery path, and telemetry hold
together at a representative size and under concurrent read load.

## Reference environment

| Property | Value |
| --- | --- |
| Host | single process, real HTTP on `127.0.0.1`, stdlib threaded server |
| Platform | Linux 6.17.0-1022-azure, x86_64 |
| Python | 3.12.3 |
| Database | SQLite 3.45.1, WAL journal, `synchronous=FULL`, single writer |
| Auth | HMAC-signed bearer tokens (the production verifier) |

## Dataset and provenance

The load corpus is the Layer 15 portfolio (`product_proof/dataset.py`, proven
in `evidence/product-proof.json`) repeated as **60 independent shards**, 17
records each (9 `source_a.v1` + 8 `source_b.v1`) — 1,020 records — plus one
400-record single-source batch. Total 1,420 records.

Shard `s` is a structure-preserving relabeling of the portfolio:

- amounts shift by `1000 * s`, so two shards never share an amount;
- dates shift by `3 * s` days, preserving each record's offset from its
  counterpart;
- references and record ids are suffixed `-S{s}`.

Amount equality, currency, direction, reference equality, and fingerprint
structure are preserved **inside** a shard, and no candidate can span two
shards. Each shard must therefore reproduce exactly the portfolio's outcome
distribution: 4 MATCHED, 4 MISMATCHED, 3 AMBIGUOUS, 3 DUPLICATE, 1 UNMATCHED_A,
1 UNMATCHED_B, 1 INVALID. The rehearsal asserts the observed outcome of every
one of the 1,020 sharded records against that manifest — a scaled dataset is
representative because its outcomes are *known*, not merely because it is
large.

## Measured results

Recorded in `evidence/staging-proof.json` (2026-09-11, reference environment
above).

| Check | Result |
| --- | --- |
| Per-record outcomes vs. proven manifest | 1,020 / 1,020 match, 0 divergences |
| Batch completion | 3 / 3 batches `COMPLETED` |
| Processing throughput | 95.5 records/s (1,420 records in 14.9 s) |
| Ingest throughput over HTTP | 216 records/s source_a, 217 records/s source_b |
| Concurrent read load | 8 clients x 25 requests, 1,658 req/s, **0 errors** |
| Read latency | p50 3.8 ms, p95 11.0 ms, p99 14.3 ms, max 26.6 ms |
| Late arrival (LA-1) | `UNMATCHED_A` superseded by `MATCHED`, version 1 -> 2, prior version still retrievable |
| Recovery drill | backup 0.07 s / restore 0.03 s / 10.4 MB verified snapshot, RTO margin 1,799.9 s of 1,800 s |
| Security boundary | 401 unauthenticated, 401 invalid token, 403 wrong scope, 200 authorized, correlation id echoed |
| Observability | `/v1/metrics` scraped, no identifier leaked into a label, no alert fired |

Read latency is measured per HTTP request in the client, including connection
setup, so it is an end-to-end client-observed number rather than a
server-internal timer.

## Defects this rehearsal found, and their fixes

The rehearsal is not a rubber stamp; it surfaced three real defects, each fixed
with a regression test.

1. **Shared-connection fetch race (service correctness).** Under concurrent
   load, `ReportingService` reads failed with
   `IndexError: tuple index out of range` and clients saw dropped connections.
   The persistence wrapper serialized `execute` but released the lock before
   the fetch, so an interleaved statement from another thread re-bound the
   pending rows' column metadata. `_SynchronizedConnection` now materializes
   results inside the critical section. Covered by
   `tests/test_service.py::ConcurrentReadTests`, which fails against the old
   wrapper.
2. **Transport parity for correlation ids.** The ASGI boundary echoed the
   caller's `X-Correlation-ID`; the stdlib `serve()` transport echoed the
   response body's constant probe id instead, so probe traffic was not
   traceable on the production entrypoint. The stdlib handler now echoes the
   request header and falls back to the body id. Covered by
   `tests/test_service.py::HttpProcessTests`.
3. **fsync-bound writes (SQLite default journal).** With the SQLite default
   (`journal_mode=delete`, `synchronous=full`) every commit fsyncs a journal
   file plus the database: measured at ~9 ms per commit on this host, and a
   reconciliation run commits per record at several stages. The store now runs
   **WAL with `synchronous=FULL`**, which keeps the same durability guarantee —
   a committed transaction survives power loss — while syncing only the
   write-ahead log. Pipeline throughput went from 11 records/s to 95.5
   records/s, and the full test suite from 51 s to 19 s. Backups already used
   `VACUUM INTO` and restore already handles `-wal`/`-shm` sidecars, so the
   recovery path was unaffected; `docs/database-operations.md` records the
   requirement that backups must never be a raw file copy.

Two smaller issues were fixed in the rehearsal harness itself: the late-arrival
assertion selected "the newest reconciliation row" instead of the decision
covering the late records (it passed only by accident of ordering), and the
harness parsed the `text/plain` metrics endpoint as JSON.

## D-009: numerical performance SLOs (approved)

Architecture D-009 deferred numerical SLOs until representative measurements
existed. Epic 8 produced them, so D-009 is now resolved. The numbers below are
**floors for the single-host v1.0 reference environment above**, chosen with
roughly a 4x margin against the recorded baseline so they detect a regression
without asserting capacity that has not been measured. They are not capacity
guarantees for other hardware, and they must be re-measured on a target machine
before any capacity claim is made on it.

| SLO | Target | Measured baseline |
| --- | --- | --- |
| Batch processing throughput | >= 25 records/s | 95.5 records/s |
| HTTP ingest throughput | >= 50 records/s | 216 records/s |
| Read API latency at 8 concurrent clients | p95 <= 250 ms, p99 <= 500 ms | p95 11.0 ms, p99 14.3 ms |
| Unexpected read errors under load | 0 | 0 |
| Recovery objectives | see D-014 | RTO margin 1,799.9 s |

Write throughput is deliberately **not** given an SLO: per-record durable
commits are an invariant-bearing design choice (a decision and its audit event
commit atomically), and trading durability for throughput is an architecture
decision, not an implementation detail. `synchronous=NORMAL` in WAL mode would
be roughly two orders of magnitude faster on this host and is the documented
next lever if a future decision accepts the weaker power-loss guarantee.

## Limitations

- **Single host, single process, single database file.** No multi-host
  failover, no orchestration, no load balancer, no network latency between
  tiers, no container resource limits.
- **Load profile is read-heavy.** The 200-request profile exercises read
  endpoints; write concurrency is exercised by ingest and pipeline runs but not
  under a deliberately adversarial mixed workload.
- **The filesystem is the bottleneck** for write paths, so absolute throughput
  is host-specific. The test assertions deliberately check error rates and
  correctness rather than absolute latency.
- **Late arrival covers one scenario** (an `UNMATCHED_A` leg later matched by
  its counterpart). Supersession of an existing `MATCHED` or `AMBIGUOUS`
  decision is covered by the LA-1 tests, not by this rehearsal.
- **Retention and offsite replication** are policy (D-014) and are not
  exercised here; the drill covers local backup and restore.

## Reproducing

```sh
make check            # 254 unit/integration tests, includes the staging suite
make staging-proof    # full-size rehearsal, rewrites evidence/staging-proof.json
make db-drill         # Epic 5 recovery drill against a seeded database
```

The staging suite (`tests/test_staging.py`) runs a scaled-down rehearsal
(2 shards) so it stays in the fast test path; the full-size run is the
evidence-producing command above. The suite also asserts that the gate
*reports* a problem when each checked property is violated, so the proof cannot
pass vacuously.
