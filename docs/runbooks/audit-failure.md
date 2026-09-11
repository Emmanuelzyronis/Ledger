# Runbook — Audit failure

| | |
| --- | --- |
| Alert | `LedgerAuditFailures` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
An operation failed after its business effect but before its append-only audit event, or audit writes are erroring.

## Impact
Audit history is an invariant. A gap means an action cannot be explained or defended.

## Diagnosis
Find the correlation id in the log line and the affected entity id. Confirm whether the write transaction rolled back completely (no partial business state) and whether the audit table is writable.

## Response
Do not hand-insert audit rows. Re-run the original idempotent operation if it is safe; if not, escalate and record the gap explicitly in the incident notes. Correctness of history dominates availability here.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
