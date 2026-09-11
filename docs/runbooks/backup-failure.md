# Runbook — Backup stale

| | |
| --- | --- |
| Alert | `LedgerBackupStale` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
No verified snapshot has succeeded within one hour (four times the approved 15-minute cadence).

## Impact
The approved RPO (`Architecture.md` D-014, ≤ 15 minutes) is no longer enforced. Data written since the last success is at risk.

## Diagnosis
Check the backup job output and `ledger_backup_last_success_timestamp_seconds`; run `PYTHONPATH=src python3 -m ledger.ops backup --database $LEDGER_DATABASE_PATH --output /tmp/probe.sqlite3` by hand to see the real error.

## Response
Fix the cause (volume full, wrong path, permissions, locked file) and confirm a verified snapshot lands. If backups cannot be restored, follow `database-unavailable.md` and freeze writes until the cadence is restored.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
