# Runbook — Database unavailable

| | |
| --- | --- |
| Alert | `LedgerReadinessFailing / LedgerDatabaseFailures` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
`GET /v1/ready` returns 503 with `database: unavailable`, or database operations are raising.

## Impact
Authoritative state cannot be read or written; the service is not usable even though liveness passes.

## Diagnosis
Check the volume is mounted and has free space; run `PYTHONPATH=src python3 -m ledger.ops integrity --database $LEDGER_DATABASE_PATH`. Inspect for `SQLITE_BUSY`/lock errors and confirm only one writer process owns the file.

## Response
If the file is corrupt, run `ledger.ops restore` from the most recent verified snapshot and verify with `ledger.ops integrity`. Never edit the database directly and never delete the corrupt file — preserve it for evidence.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
