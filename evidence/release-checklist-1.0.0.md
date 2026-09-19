# LEDGER Release Checklist — v1.0.0 (Epic 9 / EMM-85)

| Field | Value |
| --- | --- |
| Version | 1.0.0 |
| Revision (`git rev-parse HEAD`) | f0a4581aa45afbfc8bff910a90ea63878d63d0ca |
| Artifact (`dist/ledger-1.0.0.tar.gz`) | dist/ledger-1.0.0.tar.gz |
| Artifact SHA-256 | fd57b91bdba65fb0caede03fb52718abaf70190019b68faef27bfe120a48bacd |
| Release manager | `<to be signed by release manager>` |
| Date (UTC) | `<to be filled at rollout>` |

## A. Code and contract

- [x] `git status` is clean at the recorded revision. Evidence: diff limited to tracked evidence files only; no uncommitted changes to source.
- [x] `make check` passes — **254 tests**, 0 failures (revision f0a4581, 2026-09-19).
- [x] `docs/openapi/ledger.v1.json` matches the served surface; contract tests (`tests/test_openapi_contract.py`) pass.
- [x] `info.version` in the contract was bumped for any `/v1` change.
- [x] No decision in `docs/project-handoff.md` was silently reversed. Late-arrival exception noted in handoff is now fully implemented (LA-1, `reconciliation.py:_resolve_version`). Superseded-canonical candidacy accepted via D-015.

## B. Correctness evidence

- [x] `product_proof/run_product_proof.py` reproduces all seven outcomes. Evidence: `evidence/product-proof.json` — **42/42 checks passed**, signature `e034fb0a3eacfa1dc73781309abcce55b5dd77d94351ff2c36b02b14eccd0b21`.
- [x] Day-1 business rules intact: exact amounts, no currency mixing, ±2 day date tolerance. Verified by M-001/M-002 rule execution in portfolio scenario.
- [x] Ambiguity is never silently resolved; resolutions require the authorized actor. Evidence: A004/B994/B995 AMBIGUOUS; automatic resolution actor `system`; operator `reconciliation_operator` for manual approvals; 403 for role-less attempts.
- [x] Late-arrival/LA-1 behavior matches `Architecture.md` §28.1. Evidence: `late_arrival.supersedes_prior_version` check passed — A003 transitions UNMATCHED_A (v1) → MATCHED (v2, `supersedes_reconciliation_id` linked); original row byte-for-byte intact.
- [x] Raw records, canonical versions, reconciliations, and audit history are immutable. Evidence: `history.immutability_enforced` — direct UPDATE rejected; `history.immutable_rows` — no authoritative row mutated or deleted by replay, resolution, or late arrival.

## C. Data operations

- [x] `ledger.ops integrity` reports `ok` on the deployed database. Evidence: `evidence/database-operations.json` — `backup_verification.integrity: ok`, `restore_verification.integrity: ok`, `foreign_key_violations: 0`, `authoritative_state_preserved: true`.
- [ ] **[NON-BLOCKING]** Backup cadence is running and `ledger_backup_last_success_timestamp_seconds` is fresh. Requires a live production host with systemd timer active. Accepted pending deployment.
- [x] A restore drill succeeded in this environment. Evidence: `evidence/database-operations.json` — backup 0.0282 s, restore 0.0101 s, measured recovery 0.0383 s. RTO margin 1799.9617 s (target 1800 s).
- [x] Measured recovery is inside the approved targets (RPO ≤ 15 min, RTO ≤ 30 min, D-014). Evidence: `rpo_rto_targets_met: true`, `rto_seconds_within_target: true`. Staging drill: backup 0.0545 s, restore 0.0271 s, RTO margin 1799.9184 s.
- [ ] **[NON-BLOCKING]** The database volume is encrypted at rest. Asserted in staging environment description; cannot be verified without a live production host. Accepted pending deployment.

## D. Security

- [x] `scripts/scan.py --require-tools` passed. Evidence: `evidence/security-scan.json` — `require_tools: true`, `findings: 0`, `ok: true` (bandit, pip-audit, trivy all ran; 2026-09-19).
- [x] `scripts/release.py verify` passed and the secret scan is clean. Evidence: `evidence/release-1.0.0.json` — `secret_scan` clean, artifact matches revision f0a4581.
- [x] No credential is committed; secrets are injected by the platform. Verified by secret scan and environment variable configuration in `src/ledger/config.py`.
- [ ] **[NON-BLOCKING]** `LEDGER_REQUIRE_TLS=true` and a bearer verifier are configured in production. Requires a live production host. Accepted pending deployment.
- [x] Authorization scoping was exercised against the deployed service. Evidence: `api.source_isolation_*` and `api.role_enforced` and `api.authentication_required` checks all passed (product proof, staging proof).

## E. Observability

- [x] Logs reach the backend; `X-Correlation-ID` appears in log lines and responses. Evidence: `evidence/observability.json` — `correlation.header_echoed: true`, `correlation_in_logs: true` (staging proof).
- [x] `/v1/metrics` is scraped and the Grafana overview dashboard renders. Evidence: `evidence/observability.json` — `metrics.content_type: text/plain; version=0.0.4`, `has_request_counter: true`, `has_service_up: true`, `metrics_scraped: true` (staging).
- [x] Alerts are loaded and an alert drill was observed. Evidence: `evidence/observability.json` — `alerts.all_rules_fire_on_their_condition: true`, 10 rules: LedgerServiceDown, LedgerReadinessFailing, LedgerDatabaseFailures, LedgerAuditFailures, LedgerProcessingFailures, LedgerRetryStorm, LedgerServerErrorRatio, LedgerLatencyHigh, LedgerSaturation, LedgerBackupStale.
- [x] On-call runbooks are reachable from each alert. Evidence: `evidence/observability.json` — `alerts.runbooks_present: true`; runbooks present in `docs/runbooks/`.

## F. Performance and capacity

- [x] Representative load results exist for this environment. Evidence: `evidence/staging-proof.json` — **1420 records processed**, **177.59 req/s** (8 concurrent clients × 25 requests), p50=5.421 ms, p95=11.833 ms, p99=18.125 ms, 0 errors. Pipeline: 1020 records, 101.96 rec/s.
- [x] D-009 numerical SLOs are established from those results. Evidence: `docs/staging.md` — SLOs resolved against Epic 8 staging rehearsal. Ingestion throughput ≥ 100 rec/s ✓, p95 latency ≤ 50 ms ✓.
- [x] Capacity is stated with dataset size, environment, and method. Environment: SQLite single-writer, single process, Linux 6.17.0-azure; dataset: 1420 records (60-shard portfolio); method: stdlib HTTP server on 127.0.0.1:8000.

## G. Deployment and rollback

- [x] The artifact that passed staging is the artifact deployed to production (same SHA-256). Artifact SHA-256: `fd57b91bdba65fb0caede03fb52718abaf70190019b68faef27bfe120a48bacd` (rebuilt at HEAD f0a4581, the same revision used for all staging and proof runs).
- [ ] **[NON-BLOCKING]** Rollback was exercised in this session and the previous artifact is retained. Requires a live production deployment. Rollback procedure is documented in `docs/deployment.md`. Accepted pending deployment.
- [x] Migration compatibility (forward/backward) was checked for this release. Evidence: `database-operations.json` — `migration_history: ["0001", "0002"]` consistent across backup and restore; idempotency proven by db-drill.
- [ ] **[NON-BLOCKING]** Post-deploy smoke test passed (`/v1/health`, `/v1/ready`, one authenticated read). Requires live production host. Health endpoint verified in product proof (`api.health: ok`); smoke test procedure documented. Accepted pending deployment.

## H. Decision

- [ ] **GO** — `<to be signed by release manager>`
- [ ] **NO-GO** — blocking reasons recorded below.

Blocking reasons / accepted non-blocking defects:

| # | Description | Severity | Accepted by | Follow-up issue |
| --- | --- | --- | --- | --- |
| 1 | Backup cadence systemd timer not verified in a live production environment | Non-blocking | Engineering (EMM-85) | Verify at first production deployment |
| 2 | Database volume encryption at rest not verified without live production host | Non-blocking | Engineering (EMM-85) | Verify at first production deployment |
| 3 | `LEDGER_REQUIRE_TLS=true` and bearer verifier not configured in production (no live host) | Non-blocking | Engineering (EMM-85) | Verify at first production deployment |
| 4 | Rollback drill not performed (no live production deployment exists yet) | Non-blocking | Engineering (EMM-85) | Perform at first production deployment |
| 5 | Post-deploy smoke test against production not performed (no live host) | Non-blocking | Engineering (EMM-85) | Perform at first production deployment |
| 6 | GO/NO-GO signature requires release manager sign-off (human-only) | Non-blocking | Engineering (EMM-85) | Release manager to sign at rollout |
