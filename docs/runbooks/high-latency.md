# Runbook — High request latency

| | |
| --- | --- |
| Alert | `LedgerLatencyHigh` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
p95 request latency is above one second for ten minutes.

## Impact
Interactive reconciliation work slows down; clients may time out.

## Diagnosis
Compare the current profile against the staging capacity baseline in `evidence/`. Check `ledger_http_requests_in_flight` and the database size — full-file backups and large exports are the known heavy operations.

## Response
Do not optimize blindly. Identify the slow route and dataset size first; capacity changes require new measured evidence (Architecture §15, D-009).

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
