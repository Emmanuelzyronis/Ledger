# Runbook — Service down

| | |
| --- | --- |
| Alert | `LedgerServiceDown` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
The process is not running or is failing its liveness probe.

## Impact
No reconciliation work can be submitted, processed, or reported on.

## Diagnosis
Check the process supervisor state and the last structured log lines (`journalctl`/container logs). Look for startup config errors such as a missing `LEDGER_TOKEN_SECRET` in production, an unusable `LEDGER_DATABASE_PATH`, or a bind failure on `LEDGER_PORT`.

## Response
Fix the reported startup error and restart the process. Configuration errors are fail-closed by design: do not disable `LEDGER_REQUIRE_TLS` or the token requirement in production to get it running.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
