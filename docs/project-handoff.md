# LEDGER Project Handoff

**Generated:** 2026-09-09 UTC  
**Repository:** `/home/emmanuelzyronis/Ledger`  
**Purpose:** authoritative post-Layer-15 engineering handoff and production-readiness starting point  
**Classification:** **CORE FUNCTIONALLY COMPLETE / ARCHITECTURE CONFORMANCE EXCEPTION / PRODUCTION NOT READY**

## 1. Executive Orientation

LEDGER is a deterministic, auditable transaction reconciliation engine. It ingests independently produced records from two defined source schemas, preserves raw evidence, validates and normalizes them into an exact canonical model, generates bounded candidates, applies deterministic 1:1 matching rules, classifies seven reconciliation outcomes, creates discrepancies, records authorized resolutions, and derives reports and exports from authoritative SQLite state.

Its primary responsibility is correctness, determinism, traceability, idempotency, explainability, controlled performance, and operational visibility—not maximum match rate, general accounting, payment processing, settlement, or distributed scale.

The implemented architecture is a dependency-light Python modular monolith with an infrastructure-independent domain layer, SQLite authoritative persistence, and a framework-independent in-process API boundary. There is no production HTTP server, worker, container, deployment manifest, migration tooling, telemetry backend, or OpenAPI contract.

## 2. Product Identity

- **What:** a transaction reconciliation engine with a deliberately defined canonical model, multiple source representations, deterministic matching, ambiguity handling, immutable evidence, and auditable resolutions.
- **Who/what it serves:** engineering and reconciliation operators who must explain whether independent Source A and Source B records represent the same underlying transaction and how discrepancies were resolved.
- **Primary responsibility:** turn imperfect records from independent systems into deterministic, explainable reconciliation results while preserving evidence and decision history.
- **Architectural boundary:** first implementation is strictly 1:1 reconciliation between supported source pairs.
- **Deliberate non-goals:** general ledger, payment processor, banking core, distributed database, generic ETL, ML matching, workflow engine, multi-region system, settlement engine, 1:N/N:M reconciliation, or replacement for human decisions.

## 3. Current Repository State

- Git history contains only `9168082 Initial commit`.
- The complete Layer 1–15 work is uncommitted: `README.md` is modified, and all implementation/configuration/test/evidence directories are untracked.
- No deployment or CI files were found.
- Live baseline on 2026-09-09:
  - `pytest -q`: **114 passed in 3.58s**
  - `make check`: **passed; 114 unittest tests passed**
  - `python3 -m compileall src tests benchmarks product_proof`: **passed**
  - `git diff --check`: **passed**

### Documentation/Implementation Discrepancies

1. **Stale prompt index:** `prompts/README.md` says Layers 1–12 are complete and Layer 13 is next, while `Architecture.md`, `README.md`, implementation, tests, and evidence show Layers 1–15 implemented. The implementation and authoritative architecture state are current; the prompt index is stale.
2. **Late-arrival versioning exception:** `Architecture.md` §28 and D-007 require a late arrival to create a new linked reconciliation version and preserve `current_state` derivation through the latest non-superseded version. `docs/product-proof.md` explicitly says implemented late arrivals add new decision rows and do **not** create superseding reconciliation versions; the checked-in product proof verifies that behavior. This is an architecture-conformance exception, not a silently accepted implementation. It must be resolved before any claim that the implementation fully conforms to Architecture v1.0.

No other direct contradiction was found between the current architecture status section, implementation evidence, and product documentation.

## 4. Repository Structure

```text
Ledger/
├── AGENTS.md                     # Build rules, authority, invariants, stop conditions
├── Architecture.md               # Authoritative v1.0 architecture and decisions
├── README.md                     # Current implementation and verification summary
├── pyproject.toml                # Python package and test/check commands
├── Makefile                      # `test` and `check` entry points
├── .env.example                  # Non-secret runtime settings only
├── src/ledger/
│   ├── config.py                 # Settings and secret loading boundary
│   ├── observability.py          # Telemetry event, correlation, redaction contracts
│   ├── domain/                   # Infrastructure-independent entities and transitions
│   ├── persistence/sqlite.py     # SQLite schema, repositories, transactions, immutability
│   ├── ingestion.py              # Sources, batches, raw records, idempotency
│   ├── validation.py             # Structural/semantic/business validation
│   ├── normalization.py          # Source-to-canonical deterministic mapping
│   ├── identity.py               # Canonical JSON, hashes, raw/canonical IDs
│   ├── candidates.py             # Indexed bounded candidate generation
│   ├── matching.py               # M-001/M-002 and 1:1 conflict algorithm
│   ├── reconciliation.py         # Outcome persistence and discrepancy creation
│   ├── resolution.py             # Authorized resolution and audit orchestration
│   ├── reporting.py              # Read-only reports, health, export projections
│   └── api.py                    # Framework-independent authenticated API boundary
├── tests/                        # 114 tests across Layers 1–15
├── benchmarks/run_performance.py # Layer 13 performance harness
├── product_proof/                # Layer 15 deterministic full-product proof
├── docs/                         # Performance, failure, and product-proof evidence docs
├── evidence/                     # Checked-in benchmark and product-proof artifacts
└── prompts/                      # Historical Layer 1–15 implementation prompts
```

## 5. High-Level Architecture

```text
Source systems
  → ingestion/idempotency
  → immutable raw records
  → validation
  → deterministic normalization
  → deterministic identity
  → indexed candidate generation
  → deterministic matching
  → reconciliation classification
  → discrepancy creation
  → authorized resolution
  → append-only audit
  → read-only API/report/export projections
  → telemetry
```

- **Domain:** owns semantics, transitions, matching, outcomes, discrepancies, resolutions, invariants, and state guards.
- **Application services:** orchestrate one bounded operation at a time and emit telemetry/audit.
- **Persistence:** owns SQLite authority, transactions, constraints, append-only triggers, repositories, and atomic state-plus-audit writes.
- **API/reporting:** owns authentication integration, source scoping, role checks, read-only projections, exports, health, and the sole API mutation: resolution.
- **Observability:** owns structured event shape, bounded correlation fields, and redaction; events are not authoritative state.
- **Dependency direction:** domain remains infrastructure-independent; services depend on domain and persistence; API depends on services/reporting; no infrastructure concept leaks into domain semantics.
- **Failure boundary:** each authoritative operation commits completely or rolls back; derived candidates/reports/exports can be rebuilt.

## 6. Source of Truth

| Concern | Authority | Derived Consumers | Mutation Rule |
|---|---|---|---|
| Raw record | `raw_records` | normalization, lineage, reports/exports | Append-only; no update/delete; correction inserts successor |
| Batch state/counters | `batches` | status/reporting | Guarded state transition plus atomic audit |
| Processing attempt | `processing_attempts` | retry/reporting/audit | State transition plus atomic audit; new retries insert new attempts |
| Validation result | `validation_results` | normalization/reconciliation | Append-only by `(raw_record_id, validation_version)` |
| Canonical transaction | `canonical_transactions` | candidates/matching/reporting | Append-only immutable versions with supersession links |
| Match candidate | `match_candidates` | matching/reconciliation evidence | Rebuildable derived rows; append-only in current implementation |
| Reconciliation decision | `reconciliations` | discrepancies/reports/API | Immutable versions; approved resolution inserts superseding version |
| Discrepancy | `discrepancies` | resolutions/reports/API | Guarded state transition plus atomic audit |
| Resolution | `resolutions` | reconciliation supersession/audit/API | Immutable, one per discrepancy |
| Audit history | `audit_events` | reporting/audit API | Append-only; deterministic IDs and per-entity sequences |
| Ingestion submission | `ingestion_submissions` | idempotent replay | Result projection keyed by source/idempotency key |
| Reports | `reporting.py` queries | API/UI | Read-only, rebuildable, never authoritative |
| Exports | `reporting.export()` | external consumers | Read-only, redacted derived projection |
| Metrics/logs | telemetry sinks | operations | Observability only; never business state |
| Caches/queues | none implemented | — | Not applicable; never authoritative if added |

## 7. Domain Model

Implemented entities in `src/ledger/domain/entities.py`:

- **Source:** stable source identity, name, supported schema versions, active flag.
- **Batch:** source, external batch ID, schema, receipt timestamp, state, counters, timing/error metadata.
- **BatchCounters:** nonnegative accounting invariants across ingestion, validation, outcomes, and failures.
- **ProcessingAttempt:** processing version, state, retry lineage, timing, errors, counters.
- **RawRecord:** immutable source payload, content fingerprint, source-native ID, batch lineage, correction link.
- **ValidationResult:** versioned valid/invalid result with structured errors.
- **CanonicalTransaction:** exact `Decimal(20,4)` amount, ISO currency, direction, UTC timestamp, normalization version, canonical version/fingerprint, source/raw lineage, optional evidence fields, and canonical supersession link.
- **MatchCandidate:** ordered canonical A/B IDs, eligible rule IDs, and frozen evidence.
- **Reconciliation:** authoritative decision/version, A/B or raw-only lineage, outcome, rule version, evidence, state, supersession, resolution link.
- **Discrepancy:** one reconciliation, reason, and lifecycle state.
- **Resolution:** immutable decision type, actor, reason, evidence, optional deterministic rule version, and discrepancy/reconciliation lineage.
- **AuditEvent:** immutable entity event, actor, timestamp, sequence, stage version, metadata, state transition, and correlation lineage.

Identity/lineage:

- Raw identity is deterministic from source/schema/content fingerprint.
- Source-native IDs are namespaced by source and are not universal transaction IDs.
- Canonical ID/fingerprint derives from a fixed semantic field order.
- Corrections preserve old raw/canonical rows and link successors.
- Reconciliation versions are immutable; approved resolution creates a v2 `RESOLVED` version linked to v1.
- Late arrivals preserve prior decision rows but currently do not create the architecture-required linked superseding reconciliation version.

## 8. State Machines

### Batch

- **States:** `RECEIVED`, `VALIDATING`, `VALIDATED`, `REJECTED`, `PROCESSING`, `COMPLETED`, `PARTIAL`, `FAILED`.
- **Legal:** `RECEIVED→VALIDATING`; `VALIDATING→REJECTED|VALIDATED`; `VALIDATED→PROCESSING`; `PROCESSING→COMPLETED|PARTIAL|FAILED`; `FAILED→PROCESSING` or `PARTIAL→PROCESSING` only as a retry with a new attempt.
- **Terminal:** `COMPLETED`, `REJECTED`; `FAILED`/`PARTIAL` are terminal for their attempt but retryable through a new attempt.
- **Guards:** entering processing requires an attempt; completed cannot have failed records; partial must have failed records.
- **Persistence/audit:** state writes and audit append in one SQLite transaction; illegal transitions mutate nothing.
- **Retry/recovery:** new attempts retain prior history; interrupted stages remain retryable.

### ProcessingAttempt

- **States:** `CREATED`, `RUNNING`, `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELLED`.
- **Legal:** `CREATED→RUNNING`; `RUNNING→COMPLETED|FAILED|TIMED_OUT|CANCELLED`.
- **Terminal:** all four end states.
- **Persistence/audit:** transition and audit are atomic; terminal transitions require timestamps and valid time order.
- **Retry/recovery:** retries are new attempts linked through `retry_of_attempt_id`; no attempt retries itself.

### Reconciliation

- **States:** `CREATED`, `EVALUATING`, `MATCHED`, `MISMATCHED`, `UNMATCHED_A`, `UNMATCHED_B`, `AMBIGUOUS`, `DUPLICATE`, `INVALID`, `RESOLVED`.
- **Legal:** `CREATED→EVALUATING`; `EVALUATING` to exactly one of the seven outcomes; `MISMATCHED|AMBIGUOUS→RESOLVED` only via authorized approved resolution.
- **Terminal:** outcome states are terminal for their version; `RESOLVED` is terminal.
- **Persistence/audit:** immutable versions with audit; approved resolution inserts a superseding version, never updates v1.
- **Retry/recovery:** same decision identity/version is idempotent.

### Discrepancy

- **States:** `OPEN`, `DEFERRED`, `RESOLVED`, `REJECTED`.
- **Legal:** `OPEN→DEFERRED|RESOLVED|REJECTED`; `DEFERRED→RESOLVED|REJECTED`.
- **Terminal:** `RESOLVED`, `REJECTED`.
- **Persistence/audit:** discrepancy state, immutable resolution, reconciliation version where approved, and all required audit events commit together.
- **Retry/recovery:** duplicate resolution returns the original immutable result without new history.

## 9. Matching and Reconciliation Semantics

### Candidate Generation

Candidate generation only reduces the search space. It uses the union of:

1. exact normalized non-empty `transaction_reference`; and
2. exact `(currency, amount, UTC date)` with inclusive ±2 calendar-day probes.

Currency and fixed-point amount must match exactly. Account/description are evidence only and never exclusion keys. Candidate output is ordered by canonical IDs and retains all eligible indexes. The candidate set is complete for this exact v1.0 definition; no extra filters may be applied.

### Matching Rules (`standard_v1`)

1. **M-001:** exact transaction reference; priority 100.
2. **M-002:** exact amount + currency + ±2 UTC day window; priority 50.

If M-001 has multiple matches, the result is ambiguous and M-002 cannot break the tie. If M-001 has no match, M-002 is evaluated. A unique proposal is retained even when amount, currency, or direction differs, allowing `MISMATCHED`.

### Outcomes

- `MATCHED`: unique conflict-free proposal and amount/currency/direction comparisons pass.
- `MISMATCHED`: unique proposal, but amount/currency/direction fails.
- `UNMATCHED_A` / `UNMATCHED_B`: no proposal for that side.
- `AMBIGUOUS`: multiple candidates satisfy the highest applicable rule.
- `DUPLICATE`: same-source canonical fingerprint duplicate or 1:1 proposal conflict component.
- `INVALID`: validation failed; raw-only reconciliation lineage.

### 1:1 Enforcement

The algorithm builds a proposal graph keyed by canonical IDs. Any connected component containing degree >1 is classified `DUPLICATE`; no winner is selected. Unique conflict-free proposals become `MATCHED` or `MISMATCHED`. Components and proposals are processed in ascending canonical-ID order for determinism.

### Versioning and History

Reconciliation decisions retain rule version, evaluated timestamp, ordered candidate IDs, comparisons, selected rule where applicable, outcome, and lineage. Corrections and late arrivals add rows and never mutate prior decisions. Approved resolutions insert superseding versions. The late-arrival lack of an explicit supersession link remains an architecture exception.

## 10. Resolution and Audit

- **Types:** `AUTOMATIC`, `MANUAL_APPROVED`, `REJECTED`, `DEFERRED`.
- **Automatic authority:** actor must be `system` and a rule version is required.
- **Manual/other authority:** actor must be `reconciliation_operator`.
- **API role:** only principals with `reconciliation_operator` may call resolution.
- **Eligibility:** only `MISMATCHED` or `AMBIGUOUS` reconciliations with an open/deferred discrepancy may resolve.
- **Duplicate prevention:** one resolution per discrepancy; deterministic resolution identity retries return the original result.
- **Atomicity:** resolution, discrepancy transition, approved superseding reconciliation version, and audit events commit together.
- **Outcome semantics:** automatic/manual approved move discrepancy to `RESOLVED` and reconciliation to v2 `RESOLVED`; rejected/deferred leave reconciliation outcome unchanged and terminalize the discrepancy.
- **Audit:** append-only events with deterministic IDs, transactional sequence allocation, state transitions, actor, lineage, and no destructive overwrite.

## 11. Persistence

- **Technology:** Python standard-library SQLite; no runtime dependencies.
- **Connection:** SQLite connection with `PRAGMA foreign_keys = ON`; file or `:memory:`.
- **Transactions:** `BEGIN IMMEDIATE` writer transactions; nested service calls join an existing transaction; rollback on any exception.
- **Schema tables:** `sources`, `batches`, `processing_attempts`, `raw_records`, `raw_record_batches`, `validation_results`, `ingestion_submissions`, `canonical_transactions`, `match_candidates`, `reconciliations`, `discrepancies`, `resolutions`, `audit_events`.
- **Foreign keys:** source/batch/raw/canonical/reconciliation/discrepancy/audit lineage relationships.
- **Important uniqueness:** source/schema/raw fingerprint; source batch/schema; raw validation version; canonical raw/normalization/version; candidate pair; reconciliation pair/version; discrepancy resolution; audit entity/sequence.
- **Append-only triggers:** no update/delete on raw, validation, canonical, candidate, reconciliation, resolution, or audit.
- **Mutable tables:** batch, attempt, and discrepancy state changes occur only through guarded repository operations and atomic audit.
- **Indexes:** no explicit secondary indexes beyond primary/unique constraints were found; candidate generation builds deterministic in-memory dictionaries rather than relying on SQL indexes.
- **Migrations:** schema is created with `CREATE TABLE IF NOT EXISTS`; no versioned migration framework or migration history exists.
- **Operational readiness:** tested for functional consistency/rollback/restart but not production backup/restore, encryption, retention, capacity, corruption, failover, or operator runbooks.

## 12. API and Reporting

`LedgerAPI.handle()` is a framework-independent request handler, not a network server.

### Operations

- `GET /health`
- `GET /ready`
- `GET /reports[?batch_id=...]`
- `GET /export[?batch_id=...]`
- `POST /sources`
- `POST /batches`
- `POST /batches/{id}/records`
- `GET /batches/{id}`
- `GET /reconciliations[?batch_id=...]`
- `GET /reconciliations/{id}`
- `GET /discrepancies[?batch_id=...]`
- `GET /discrepancies/{id}`
- `GET /audit/{entity_type}/{entity_id}`
- `POST /discrepancies/{id}/resolve`

### Behavior

- Bearer authentication is delegated to an externally supplied token verifier.
- Source scoping uses principal `source_ids`; absence means unrestricted source access.
- Resolution requires `reconciliation_operator` in `roles` or singular `role`.
- API requests receive a generated or caller-provided `X-Correlation-ID`.
- Valid responses use `{ data, correlation_id }`; API errors use `{ error: { code, message }, correlation_id }`.
- Known bad input/domain exceptions generally return 400; missing resources return 404; auth failures 401; authorization failures 403; database unavailable readiness returns 503.
- Ingestion supports an idempotency key; replay returns the original logical result and marks duplicate submission.
- Reports count authoritative reconciliation outcomes and discrepancies and include an audit watermark.
- Export is read-only, redacts payload/description/secret/token/credential keys, and never contains raw payload values.
- Health reports application/database status; readiness returns 503 if database is unavailable.

### Missing

- No network HTTP server or ASGI/WSGI adapter.
- No formal OpenAPI document, generated contract, API versioning policy, contract tests, request-size limits, rate limits, TLS termination, CORS policy, or security headers.

## 13. Security

### Verified Controls

- Bearer token verifier boundary with 401 for missing/invalid tokens.
- `reconciliation_operator` authorization for resolution.
- Source and batch scoping for reporting, records, reconciliations, discrepancies, and relevant audit subjects.
- Input object/required-field checks and domain validation.
- Secrets have no source-code defaults and must come from runtime environment.
- Frozen domain mappings and strict amount/date/currency/direction validation.
- Export redaction for payload/description/secrets/tokens/credentials.
- Telemetry redaction for sensitive keys.
- SQLite foreign keys, constraints, append-only triggers, and transactional audit.
- Failure tests cover authorization and redaction behavior.

### Production Gaps

- No production identity provider/token verifier implementation.
- No TLS, CORS, security headers, request limits, rate limits, or audit-access controls beyond current principal scoping.
- No payload byte/depth/size limits or reusable untrusted-input parser hardening beyond the current schema checks.
- No dependency scanning, container scanning, image hardening, secret rotation, or vulnerability policy.
- No least-privilege database users/read-write separation.
- No encryption-at-rest, retention policy, backup/restore controls, or audit tamper protection beyond SQLite triggers.
- No formal threat model, security review, penetration test, or production authorization test suite.

## 14. Observability

Implemented structured `TelemetryEvent` names include:

- `ledger.ingestion.record_accepted`
- `ledger.ingestion.record_invalid`
- `ledger.ingestion.submission_duplicate`
- `ledger.validation.record_valid`
- `ledger.validation.record_invalid`
- `ledger.normalization.completed`
- `ledger.identity.verified`
- `ledger.candidates.generated`
- `ledger.resolution.applied`
- `ledger.api.request`

Correlation fields are bounded to `batch_id`, `attempt_id`, `record_id`, and `reconciliation_id`; API events carry correlation ID, method, path, and status. Sensitive keys are recursively redacted. The only sink is in-memory for tests/local use.

Missing production observability:

- No external structured-log sink.
- No metrics backend, counters, histograms, dashboards, alerts, SLOs, error budgets, or retention policy.
- No operational alert definitions for database failure, processing failure, retries, latency, queue depth, audit failure, or service saturation.
- No trace propagation beyond explicit correlation IDs.

## 15. Performance Evidence

**Harness:** `benchmarks/run_performance.py`  
**Method:** real SQLite-backed services; one warm-up and five measured iterations; deterministic fixtures; median, nearest-rank p95, throughput, peak `tracemalloc` memory, candidate distribution, correctness signature, and environment metadata.  
**Dataset:** 32, 64, and 128 records per source (64, 128, 256 total).  
**Environment:** Linux x86_64, Python 3.12.3, SQLite 3.45.1.

Observed 128-per-source baseline:

| Stage | Median seconds | p95 seconds | Records/sec |
|---|---:|---:|---:|
| Ingestion | 0.092346 | 0.094536 | 2772.18 |
| Validation | 0.091478 | 0.092269 | 2798.46 |
| Normalization | 0.076090 | 0.076264 | 3364.42 |
| Identity | 0.008922 | 0.009102 | 28691.70 |
| Candidate generation | 0.049223 | 0.050136 | 5200.78 |
| Matching | 0.027924 | 0.030611 | 9167.64 |
| Reconciliation | 0.035852 | 0.038306 | 7140.55 |
| Resolution | 0.000945 | 0.000966 | 271019.37 |

Candidate counts were 32, 64, and 128 versus all-pairs 1,024, 4,096, and 16,384. Peak memory ranged from 366,458 to 1,362,501 bytes. Correctness signatures were stable across measured iterations. Candidate count must not exceed five times pair count in the harness.

**Limitations:** small datasets, one machine, no concurrent load, no production hardware, no SLOs, and no end-to-end service/network/deployment overhead. D-009 numerical SLOs remain intentionally deferred.

## 16. Failure Verification

`tests/test_failure_verification.py` injects failures at service/repository boundaries after earlier writes where possible, then proves rollback and retry:

- database interruption during ingestion;
- partial/interrupted batch;
- validation failure/recovery;
- normalization audit failure;
- identity/corrupt lineage rejection;
- candidate persistence failure;
- reconciliation/discrepancy failure;
- late audit failure;
- processing-attempt failure/retry;
- invalid/corrupt input;
- illegal terminal transitions;
- resolution mid-commit audit failure.

Observed contract: authoritative state and audit either commit together or leave no partial state; retries are idempotent; terminal/failed attempts remain immutable; new attempts preserve lineage.

Limitations: Python-boundary fault injection only; no process kill, disk full, power loss, network partition, real OS durability test, or workflow-controller recovery.

## 17. Product Proof

**Harness:** `product_proof/run_product_proof.py`  
**Regression:** `tests/test_product_proof.py`  
**Evidence:** `evidence/product-proof.json`  
**Suite version:** `product_proof_v1`  
**Signature:** `a510679dde747834c310f532343dd200744117206fe0010d77f15591bd9c8cce`  
**Fixture manifest SHA-256:** `8902b2efb05940fcdb38bcca3c298a01e1eac69cc9bfac117321d96c100cca3e`

The proof uses real SQLite services and deterministic fixed clock. Portfolio evidence demonstrates all seven outcomes:

- `MATCHED`: A001/B991 and A002/B992.
- `MISMATCHED`: A006/B996 and A007/B997.
- `UNMATCHED_A`: A003.
- `UNMATCHED_B`: B993.
- `AMBIGUOUS`: A004/B994/B995.
- `DUPLICATE`: D-A1/D-A2/D-B1.
- `INVALID`: A005.

It also proves:

- automatic/manual/deferred/rejected resolution workflows and one residual open item;
- API reporting, source isolation, role checks, unauthenticated rejection, and export redaction;
- ingestion duplicate and pipeline replay idempotency;
- late arrival preserving the old decision and adding a matched decision;
- raw immutability under direct update probe;
- correction preserving raw/canonical/decision history;
- SQLite file reopen/restart signature equality;
- structured redacted telemetry;
- all twelve invariants with product-level evidence.

Product proof is **VERIFIED COMPLETE for the implemented contract**, but its late-arrival supersession behavior is a documented architecture exception. No production readiness is claimed.

## 18. Invariants

All twelve established invariants have automated and product-proof evidence.

| ID | Name | Enforcement | Testing/Evidence | Status |
|---|---|---|---|---|
| L-INV-001 | Raw immutability | append-only triggers, frozen payloads | persistence/failure/product proof | VERIFIED COMPLETE |
| L-INV-002 | Deterministic normalization | versioned mapper/fingerprint | normalization, replay, product proof | VERIFIED COMPLETE |
| L-INV-003 | Deterministic identity | canonical JSON + SHA-256 | identity/failure/product proof | VERIFIED COMPLETE |
| L-INV-004 | Idempotent ingestion | submissions/raw uniqueness | ingestion/failure/product proof | VERIFIED COMPLETE |
| L-INV-005 | No silent loss | states/counters/outcomes | domain/pipeline/product proof | VERIFIED COMPLETE |
| L-INV-006 | Explainable reconciliation | rule/version/evidence/candidate order | matching/reconciliation/product proof | VERIFIED COMPLETE |
| L-INV-007 | No automatic ambiguous match | ambiguity branch/authorized resolution | matching/resolution/product proof | VERIFIED COMPLETE |
| L-INV-008 | Audit preservation | append-only/transactional audit | persistence/failure/product proof | VERIFIED COMPLETE |
| L-INV-009 | 1:1 enforcement | conflict graph/no winner | matching/reconciliation/failure/product proof | VERIFIED COMPLETE |
| L-INV-010 | Historical preservation | immutable versions/supersession | correction/late arrival/product proof | VERIFIED COMPLETE, with late-arrival architecture exception |
| L-INV-011 | State-machine validity | domain transition guards | domain/failure/product proof | VERIFIED COMPLETE |
| L-INV-012 | Source identity isolation | namespaced IDs/source scoping | identity/candidates/API/product proof | VERIFIED COMPLETE |

## 19. Completion Matrix

| Area | Status | Evidence | Remaining Work |
|---|---|---|---|
| Foundation | VERIFIED COMPLETE | tests, config/telemetry | production sink/settings |
| Domain | VERIFIED COMPLETE | 114 tests | none for core scope |
| Persistence | IMPLEMENTED BUT NOT PRODUCTION-VERIFIED | persistence/failure tests | migrations, operations, backup |
| Ingestion | VERIFIED COMPLETE | ingestion/failure/product proof | production connector absent by scope |
| Validation | VERIFIED COMPLETE | validation/failure/product proof | production payload limits |
| Normalization | VERIFIED COMPLETE | normalization/product proof | none for core scope |
| Identity | VERIFIED COMPLETE | identity/failure/product proof | none for core scope |
| Candidate Generation | VERIFIED COMPLETE | candidates/performance/product proof | no persistent SQL indexes |
| Matching | VERIFIED COMPLETE | matching/product proof | none for core scope |
| Reconciliation | PARTIALLY IMPLEMENTED | product proof | late-arrival supersession exception |
| Resolution | VERIFIED COMPLETE | resolution/product proof | production identity/roles |
| Audit | VERIFIED COMPLETE | persistence/failure/product proof | operational retention/tamper controls |
| API | IMPLEMENTED BUT NOT PRODUCTION-VERIFIED | API/product proof | server, contracts, hardening |
| Reporting | VERIFIED COMPLETE | product proof | production projections optional |
| Performance | IMPLEMENTED BUT NOT PRODUCTION-VERIFIED | Layer 13 evidence | representative/SLO decisions |
| Failure Verification | VERIFIED COMPLETE for test fault model | Layer 14 | OS/process/disk fault model |
| Product Proof | VERIFIED COMPLETE with exception | Layer 15 | resolve architecture conflict |
| Security | PARTIALLY IMPLEMENTED | API tests/redaction | production hardening |
| Deployment | NOT IMPLEMENTED | no files | full service foundation |
| Database Operations | NOT IMPLEMENTED | no operational docs | backup/restore/RPO/RTO/runbooks |
| Observability | PARTIALLY IMPLEMENTED | in-memory telemetry | backend/dashboards/alerts |
| API Documentation | NOT IMPLEMENTED | no OpenAPI | formal contract |
| Release Engineering | NOT IMPLEMENTED | no release process | artifacts/checklist |
| Frontend | NOT IMPLEMENTED | no frontend | unnecessary for current API/reporting scope |

## 20. Production Readiness

### Complete

- core deterministic pipeline and domain invariants;
- SQLite authoritative persistence and rollback semantics;
- API boundary with bearer-verifier integration, source scoping, resolution role, reporting/export;
- performance and product-proof evidence;
- local test/check commands.

### Partial

- configuration: development/test/production values and secret loader, but no production runtime integration;
- security: tested API/domain controls, but no production identity/TLS/hardening;
- observability: structured redacted events and health, but no backend/dashboards/alerts;
- persistence: strong functional/transactional tests, but no production operations;
- performance: reproducible baseline, but no representative production SLO.

### Missing

- service entrypoint and HTTP server;
- worker/process model and orchestration controller;
- deployment manifests/container/security scanning;
- OpenAPI, API versioning, contract tests;
- request limits, rate limits, CORS, security headers, TLS;
- backup, restore, encryption, retention, corruption recovery, RPO/RTO;
- telemetry backend, dashboards, alerts, runbooks;
- staging environment and production rehearsal;
- release artifacts, release checklist, rollback plan;
- database migration/versioned schema management.

## 21. Known Limitations

- SQLite is the only implemented database; no production database choice is made.
- No migration framework; schema creation is not a production migration strategy.
- No service process, HTTP network layer, worker, scheduler, or long-running orchestration.
- No production authentication provider; token verification is injected.
- No formal API contract/OpenAPI.
- No request limits/rate limits/CORS/security headers/TLS.
- No external telemetry sink, metrics, dashboards, alerts, or operational runbooks.
- No backup/restore, encryption-at-rest, retention, RPO/RTO, or restore rehearsal.
- Benchmarks are small and local; no SLOs.
- Failure tests use Python-boundary fault injection.
- Batch counters do not own reconciliation outcomes; reconciliations remain authoritative.
- Superseded canonical versions remain in the candidate/matching graph; correction re-evaluation adds decisions.
- Late arrivals add new decisions but do not create the architecture-required linked reconciliation version.
- No frontend exists; current product definition is API/reporting-oriented.

## 22. Open Decisions

| ID | Decision | Status | Why Open | Depends On | Recommended Decision Point |
|---|---|---|---|---|---|
| D-009 | Performance SLO | DEFERRED | representative production measurements absent | service/deployment/load model | after staging benchmark |
| PRD-001 | Production database | OPEN | SQLite is functional but not operationally selected | backup/RPO/RTO/capacity | Production Service Foundation epic |
| PRD-002 | Service/worker model | OPEN | only in-process runner/API exists | traffic, batch size, recovery | Production Service Foundation epic |
| PRD-003 | Identity provider/token verifier | OPEN | injected verifier only | customer/infrastructure requirements | Security Hardening epic |
| PRD-004 | API versioning and OpenAPI strategy | OPEN | no formal contract | consumers/release policy | API Contract epic |
| PRD-005 | Production telemetry backend | OPEN | only in-memory sink | infrastructure selection | Observability epic |
| PRD-006 | Backup/restore and RPO/RTO | OPEN | no operational controls | database/service choice | Database Operations epic |
| PRD-007 | Late-arrival version semantics | OPEN CONFLICT | architecture and implementation differ | architecture owner decision | before release candidate |
| PRD-008 | Frontend need | OPEN PRODUCT DECISION | API/reporting is current interface | customer requirements | after API contract |

## 23. Risks

| Risk | Severity | Evidence | Impact | Mitigation | Blocks Production |
|---|---|---|---|---|---|
| No service entrypoint/HTTP server | Critical | no server/deployment files | cannot serve production traffic | Production Service Foundation | Yes |
| No production authentication/TLS | Critical | injected verifier, no TLS | sensitive financial data exposure | Security Hardening | Yes |
| No backup/restore/RPO/RTO | Critical | no operational evidence | irreversible data loss risk | Database Operations | Yes |
| Late-arrival architecture conflict | High | Architecture §28 vs product proof | incorrect current-state/history semantics | architecture decision/remediation | Yes |
| No migrations/schema operations | High | only `CREATE IF NOT EXISTS` | unsafe upgrades | migration framework/runbooks | Yes |
| No telemetry/alerting | High | in-memory sink only | undetected outages/data issues | observability backend | Yes |
| No API contract/versioning | High | no OpenAPI | consumer breakage/security ambiguity | API Contract | Yes |
| No production performance/SLO | Medium | local small benchmark | capacity surprises | staging load test | Yes |
| No payload/rate/request limits | High | API implementation gap | DoS/data exposure | hardening/limits | Yes |
| No dependency/container scanning | Medium | no config/files | vulnerable artifacts | release engineering | Yes |
| Uncommitted repository state | Medium | git status | handoff/version loss | commit/tag baseline | No, but urgent |
| Stale prompt index | Low | prompts README | engineer confusion | documentation update | No |

## 24. Recommended Post-Layer-15 Roadmap

1. **Baseline Commit and Architecture Decision** — commit/tag current state, resolve late-arrival conflict, refresh stale docs.
2. **Production Service Foundation** — choose runtime/service model, add server entrypoint, config binding, graceful shutdown, health/readiness, worker/process model.
3. **Security Hardening** — production token verifier, TLS, request limits, rate limits, CORS, headers, payload limits, secrets, least privilege, threat model.
4. **API Contract** — OpenAPI, versioning, request/response schemas, error contract, contract tests, export controls.
5. **Database Operations / Backup & Recovery** — production database decision or SQLite operational boundary, migrations, backup/restore, retention, encryption, RPO/RTO, corruption drills.
6. **Production Observability** — structured logs, metrics, traces, dashboards, alerts, runbooks, redaction tests.
7. **Deployment / Infrastructure** — container or deployment target, security scanning, environment promotion, secrets, rollback.
8. **Staging** — representative fixtures/load, auth integration, database rehearsal, operational verification.
9. **Production Rehearsal** — failure injection, restore, alert response, performance/capacity, release rollback.
10. **Release Candidate** — release checklist, evidence package, approvals, versioned artifacts.
11. **Production Release** — controlled rollout, monitoring, incident response, post-release review.

Frontend is **unnecessary** for the current product definition and should not be added unless product requirements change.

## 25. Linear Breakdown

**Project:** LEDGER Production Readiness  
**Critical Path:** Issues 1 → 2 → 3/4/5 (parallelizable after architecture correction) → 6 → 7 → 8 → 9.

### Epic 1 — Baseline and Architecture Correction

#### Issue 1: Commit Layer 15 baseline and resolve late-arrival semantics
- **Objective:** preserve the verified core and decide whether to revise architecture or remediate implementation.
- **Why:** all work is uncommitted, and Architecture §28 conflicts with implemented late-arrival behavior.
- **Scope:** commit/tag current state; update stale prompt index; obtain architecture decision; implement only the selected semantics; add regression/evidence.
- **Dependencies:** none.
- **Acceptance:** clean git history/tag; one authoritative late-arrival rule; tests and product-proof evidence updated.
- **Verification:** full test/check baseline and product proof.
- **Evidence:** commit/tag, test output, updated architecture/product proof.
- **Priority:** Critical.
- **Blocking:** production.
- **DoD:** no contradiction between architecture, docs, implementation, and evidence.

### Epic 2 — Production Service Foundation

#### Issue 2: Build production service entrypoint and process model
- **Objective:** expose LEDGER through a supported HTTP service with lifecycle management.
- **Why:** current API is framework-independent but has no server or operational process model.
- **Scope:** choose service framework/ASGI strategy; bind validated settings; add start/stop/graceful shutdown; wire health/readiness; define worker/batch execution model; add structured startup logs.
- **Dependencies:** Issue 1.
- **Acceptance:** service starts from config, serves API, health/readiness works, shutdown drains cleanly, tests cover lifecycle.
- **Verification:** integration tests, local run, process restart test.
- **Evidence:** deployment-neutral run instructions and test results.
- **Priority:** Critical.
- **Blocking:** all deployment work.
- **DoD:** no core behavior changes; production service boundary is reproducible.

### Epic 3 — Security Hardening

#### Issue 3: Harden authentication, authorization, and request boundaries
- **Objective:** protect sensitive reconciliation data in a production network context.
- **Why:** current controls are tested domain/API patterns, not production security.
- **Scope:** production token verifier; least-privilege principal model; TLS termination; request body/depth/size limits; rate limiting; CORS; security headers; authorization audit; export controls; threat model.
- **Dependencies:** Issue 2.
- **Acceptance:** unauthenticated/invalid/over-limit/cross-scope requests fail safely; operator role enforced; no sensitive data in logs.
- **Verification:** auth/limit/security-header tests and security review.
- **Evidence:** threat model, test report, scan results.
- **Priority:** Critical.
- **Blocking:** staging/release.
- **DoD:** security controls are explicit, tested, and documented.

### Epic 4 — API Contract

#### Issue 4: Publish versioned OpenAPI and contract tests
- **Objective:** make the API consumable and stable.
- **Why:** no formal schema/version/error contract exists.
- **Scope:** OpenAPI 3.1 document; schema models; status/error contract; auth/security schemes; versioning policy; examples; contract tests for every endpoint.
- **Dependencies:** Issue 2; coordinate with Issue 3.
- **Acceptance:** every implemented operation is documented and contract-tested; examples validate; incompatible changes are explicit.
- **Verification:** OpenAPI validation and contract suite.
- **Evidence:** OpenAPI artifact and test report.
- **Priority:** High.
- **Blocking:** external integration/staging.
- **DoD:** implementation and contract cannot drift silently.

### Epic 5 — Database Operations

#### Issue 5: Establish migration, backup, and recovery operations
- **Objective:** make authoritative data operationally safe.
- **Why:** current schema creation and tests do not prove upgrade/restore durability.
- **Scope:** production database decision; versioned migrations; backup/restore; retention; encryption; least-privilege users; corruption/failure drills; RPO/RTO targets; runbook.
- **Dependencies:** Issue 1; database choice may follow Issue 2.
- **Acceptance:** upgrade from current schema succeeds; backup/restore preserves authority and audit; measured RPO/RTO meet approved targets.
- **Verification:** migration/restore/restart tests on representative data.
- **Evidence:** runbook and recorded drill output.
- **Priority:** Critical.
- **Blocking:** release.
- **DoD:** recovery is demonstrable, timed, and documented.

### Epic 6 — Production Observability

#### Issue 6: Implement production telemetry, dashboards, and alerts
- **Objective:** make operational health and failures visible.
- **Why:** only an in-memory sink exists.
- **Scope:** structured log backend; metrics; bounded labels; correlation/trace propagation; dashboards; alerts for availability, DB failures, processing failures, retries, latency, audit failures, and saturation; retention/redaction.
- **Dependencies:** Issues 2 and 5.
- **Acceptance:** events reach production backend; alerts fire in test; dashboards expose required signals; no payloads/secrets leak.
- **Verification:** telemetry integration test and alert drill.
- **Evidence:** dashboard configurations and alert test output.
- **Priority:** High.
- **Blocking:** production rehearsal.
- **DoD:** on-call engineers can detect and diagnose primary failures.

### Epic 7 — Deployment and Release Engineering

#### Issue 7: Create deployment artifacts and release pipeline
- **Objective:** package and deploy LEDGER reproducibly.
- **Why:** no deployment/CI/release infrastructure exists.
- **Scope:** container or deployment manifest; dependency pinning; SAST/dependency/container scans; environment promotion; secrets integration; release artifacts; rollback; release checklist.
- **Dependencies:** Issues 2–6.
- **Acceptance:** one command builds a scanned artifact; staging deploy succeeds; rollback is tested.
- **Verification:** build/deploy/scan/rollback pipeline.
- **Evidence:** artifacts, scan report, pipeline run.
- **Priority:** High.
- **Blocking:** staging/release.
- **DoD:** release is reproducible and auditable.

### Epic 8 — Staging and Production Readiness

#### Issue 8: Run staging integration and representative load proof
- **Objective:** verify the complete deployed system under representative conditions.
- **Why:** local tests/benchmarks do not prove production operation.
- **Scope:** staging environment; real auth; representative datasets; load/concurrency; long batches; late arrivals/corrections; telemetry; backup/restore; failure drills.
- **Dependencies:** Issues 2–7.
- **Acceptance:** functional, security, performance, recovery, and observability criteria pass or non-blockers are recorded.
- **Verification:** end-to-end staging suite and rehearsal report.
- **Evidence:** staging report with environment, dataset, results, defects.
- **Priority:** Critical.
- **Blocking:** release candidate.
- **DoD:** production readiness decision is evidence-based.

#### Issue 9: Approve release candidate and production rollout
- **Objective:** release only after evidence and controls are complete.
- **Why:** production release requires explicit approval and rollback readiness.
- **Scope:** release candidate tag; final test/scan/evidence package; go/no-go checklist; controlled rollout; monitoring; incident response; post-release review.
- **Dependencies:** Issue 8.
- **Acceptance:** all critical blockers closed; approved checklist; rollback tested.
- **Verification:** final full regression plus deployment verification.
- **Evidence:** signed release checklist and rollout record.
- **Priority:** Critical.
- **Blocking:** production.
- **DoD:** production state is monitored, supportable, and reversible.

## 26. Recommended Execution Rule

For every issue:

1. **Contract:** write or update the explicit architecture/API/operational contract before code.
2. **Execute:** implement only the issue scope.
3. **Verify:** run focused tests, full regression, compile check, and relevant operational proof.
4. **Fix required defects:** defects that violate invariants, contracts, security, or release blockers must be fixed before advancing.
5. **Record non-blocking defects:** log them with owner, severity, and follow-up issue; do not silently defer.
6. **Advance:** only after evidence satisfies the issue DoD.

Preserve the existing layer-scoped defect rule: never weaken an invariant or architecture contract to make a test pass.

## 27. Verification Commands

```sh
pytest -q
make check
python3 -m compileall src tests benchmarks product_proof
git diff --check
```

Project-specific reproducible evidence commands:

```sh
PYTHONPATH=src python3 product_proof/run_product_proof.py
PYTHONPATH=src python3 benchmarks/run_performance.py
```

Current live results for the first four commands are all passing. The checked-in product-proof and performance artifacts are historical reproducible evidence; rerun them on the target machine before using them for capacity or release decisions.

## 28. Evidence Locations

- Architecture: `Architecture.md`
- Build rules: `AGENTS.md`
- Current summary: `README.md`
- Performance harness: `benchmarks/run_performance.py`
- Performance method: `docs/performance.md`
- Performance evidence: `evidence/performance-baseline.json`, `evidence/performance-run.txt`
- Failure evidence: `tests/test_failure_verification.py`, `docs/failure-verification.md`
- Product fixtures: `product_proof/`
- Product method: `docs/product-proof.md`
- Product evidence: `evidence/product-proof.json`
- Full regression: `tests/`
- Persistence/schema: `src/ledger/persistence/sqlite.py`
- API/reporting: `src/ledger/api.py`, `src/ledger/reporting.py`

## 29. Final Executive Summary

### Current State

Layers 1–15 are implemented and the full 114-test baseline passes. The core pipeline, SQLite authority, deterministic matching, resolution/audit, reporting boundary, failure semantics, performance harness, and product proof are present. All work is currently uncommitted.

### What Is Proven

The implemented product contract can deterministically ingest, preserve, validate, normalize, identify, candidate-generate, match, reconcile, resolve, audit, and report all seven outcomes with immutable history, idempotent retry, source isolation, export redaction, correction/late-arrival preservation, restart replay, and telemetry redaction.

### What Is Not Proven

No production service, deployment, authentication provider, TLS, request hardening, migrations, backup/restore, telemetry backend, alerts, representative load, staging behavior, or release process is proven. No numerical SLO is defined. The late-arrival implementation conflicts with Architecture §28/D-007.

### Production Blockers

Service entrypoint, production security, API contract, database operations/backup, observability, deployment, staging rehearsal, and the late-arrival architecture conflict.

### Critical Path

Commit and architecture correction → service foundation → security/API/database/observability workstreams → deployment → staging rehearsal → release candidate → production release.

### Major Risks

Critical: no production service, security, or backup/recovery. High: architecture conflict, no migrations, no API contract, no limits, no operational telemetry. Medium: uncommitted work and unproven capacity.

### Recommended Next Action

Commit/tag the Layer 15 baseline, update the stale prompt index, and obtain an explicit architecture decision for late-arrival reconciliation versioning before starting the Production Service Foundation epic.

### Overall Assessment

**CORE FUNCTIONALLY COMPLETE / ARCHITECTURE CONFORMANCE EXCEPTION / PRODUCTION NOT READY**
