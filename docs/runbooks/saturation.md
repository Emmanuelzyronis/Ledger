# Runbook — Saturation

| | |
| --- | --- |
| Alert | `LedgerSaturation` |
| Severity | see `docs/observability/alerts/ledger-alerts.yaml` |
| Owner | LEDGER on-call |
| Evidence | `docs/observability.md`, `evidence/` |

## Symptom
In-flight requests exceed 80% of `LEDGER_MAX_CONCURRENT_REQUESTS` for five minutes.

## Impact
Requests queue in front of the single-process request lock; latency rises while throughput plateaus.

## Diagnosis
Confirm whether load is legitimate (a bulk ingest) or a retry loop. Check `rate(ledger_http_requests_total[5m])` by route and mitigate client retries.

## Response
Shed or schedule bulk load outside interactive hours, or raise the concurrency limit only with measured evidence that the database tolerates it. Scaling out is an architecture change because the store is single-writer.

## Verification
Re-check the alert series and the dashboard panel `LEDGER Service Overview`. The alert
must resolve within one evaluation interval (15 s) after the fix, and
`ledger_service_up`/`ledger_ready_state` must both be 1.

## Escalation
If the condition persists after the steps above, treat it as an incident: roll back to the
previous release artifact (Epic 7 rollback) and restore the last verified snapshot
(`docs/database-operations.md` §3).
