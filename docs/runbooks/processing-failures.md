# Runbook — Processing failures / retry storm

| | |
| --- | --- |
| Alert | `LedgerProcessingFailures / LedgerRetryStorm` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
A pipeline stage is failing or retrying repeatedly for one or more batches.

## Impact
Batches remain in their pre-failure state; reconciliation results are delayed.

## Diagnosis
Read the `stage` label and the correlation ids on the failure events. Inspect the affected batch with `GET /v1/batches/{batch_id}` and confirm its state is a legal state rather than a partial write.

## Response
Fix the stage-level cause, then re-run the batch with the idempotent operator path documented in `docs/service.md` (Batch progression). Re-running is safe: ingestion is idempotent and no accepted input is dropped.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
