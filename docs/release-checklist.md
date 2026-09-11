# LEDGER Release Checklist (Epic 9 / EMM-85)

Copy this file to `evidence/release-checklist-<version>.md`, fill every field,
and commit it with the release. A line is only checked when the linked evidence
exists at the recorded revision. **Record the revision and version at the top.**

| Field | Value |
| --- | --- |
| Version | |
| Revision (`git rev-parse HEAD`) | |
| Artifact (`dist/ledger-<version>.tar.gz`) | |
| Artifact SHA-256 | |
| Release manager | |
| Date (UTC) | |

## A. Code and contract

- [ ] `git status` is clean at the recorded revision.
- [ ] `make check` passes (record the test count).
- [ ] `docs/openapi/ledger.v1.json` matches the served surface; contract tests pass.
- [ ] `info.version` in the contract was bumped for any `/v1` change.
- [ ] No decision in `docs/project-handoff.md` was silently reversed.

## B. Correctness evidence

- [ ] `product_proof/run_product_proof.py` reproduces all seven outcomes.
- [ ] Day-1 business rules intact: exact amounts, no currency mixing, ±2 day date tolerance.
- [ ] Ambiguity is never silently resolved; resolutions require the authorized actor.
- [ ] Late-arrival/LA-1 behavior matches `Architecture.md` §28.1.
- [ ] Raw records, canonical versions, reconciliations, and audit history are immutable.

## C. Data operations

- [ ] `ledger.ops integrity` reports `ok` on the deployed database.
- [ ] Backup cadence is running and `ledger_backup_last_success_timestamp_seconds` is fresh.
- [ ] A restore drill succeeded in this environment (record the measured RTO).
- [ ] Measured recovery is inside the approved targets (RPO ≤ 15 min, RTO ≤ 30 min, D-014).
- [ ] The database volume is encrypted at rest (asserted in staging, not assumed).

## D. Security

- [ ] `scripts/scan.py --require-tools` passed (bandit, pip-audit, trivy recorded).
- [ ] `scripts/release.py verify` passed and the secret scan is clean.
- [ ] No credential is committed; secrets are injected by the platform.
- [ ] `LEDGER_REQUIRE_TLS=true` and a bearer verifier are configured in production.
- [ ] Authorization scoping was exercised against the deployed service.

## E. Observability

- [ ] Logs reach the backend; `X-Correlation-ID` appears in log lines and responses.
- [ ] `/v1/metrics` is scraped and the Grafana overview dashboard renders.
- [ ] Alerts are loaded and an alert drill was observed.
- [ ] On-call runbooks are reachable from each alert.

## F. Performance and capacity

- [ ] Representative load results exist for this environment (record dataset size, method, result).
- [ ] D-009 numerical SLOs are either established from those results or explicitly still deferred.
- [ ] Capacity is stated with dataset size, environment, and method (`AGENTS.md` §15).

## G. Deployment and rollback

- [ ] The artifact that passed staging is the artifact deployed to production (same SHA-256).
- [ ] Rollback was exercised in this session and the previous artifact is retained.
- [ ] Migration compatibility (forward/backward) was checked for this release.
- [ ] Post-deploy smoke test passed (`/v1/health`, `/v1/ready`, one authenticated read).

## H. Decision

- [ ] **GO**
- [ ] **NO-GO** — blocking reasons recorded below.

Blocking reasons / accepted non-blocking defects:

| # | Description | Severity | Accepted by | Follow-up issue |
| --- | --- | --- | --- | --- |
| 1 | | | | |
