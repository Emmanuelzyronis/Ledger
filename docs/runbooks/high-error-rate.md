# Runbook — Elevated 5xx ratio

| | |
| --- | --- |
| Alert | `LedgerServerErrorRatio` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
More than 2% of HTTP requests are returning 5xx over five minutes.

## Impact
Requests are failing at the service boundary; clients may retry and amplify load.

## Diagnosis
Break 5xx down by `route` on the dashboard, then correlate with `ledger_db_failures_total` and `ledger_processing_failures_total`.

## Response
If the cause is the database, follow `database-unavailable.md`. If it is one route, check the last deployment for a contract or code regression and roll back if needed.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
