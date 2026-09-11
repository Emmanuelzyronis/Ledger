# LEDGER Observability (Epic 6 / EMM-82)

This document is the operator contract for LEDGER telemetry. It covers the
logging boundary, the metric surface and its bounded labels, correlation,
redaction, retention, dashboards, alerts, and runbooks.

Code lives in `src/ledger/observability.py` (sinks, the metric registry, the
retention/redaction policy), `src/ledger/alerts.py` (alert rules as data), and
the service boundary in `src/ledger/service.py`. Tests are in
`tests/test_observability.py`.

**Telemetry is never authoritative business state.** It is a derived projection
for operators (Architecture §4, D-013). Losing telemetry must never lose a
transaction, and no alert ever changes business state.

## 1. What LEDGER emits

| Signal | Shape | Where |
| --- | --- | --- |
| Lifecycle and domain events | one redacted JSON object per line (`TelemetryEvent`) | stdout (`JsonLogSink`) |
| Metrics | Prometheus text exposition | `GET /v1/metrics` |
| Correlation | `X-Correlation-ID` (accepted and echoed); also in every JSON body | all `/v1` responses |
| Alerts | Prometheus rule file generated from rule data | `docs/observability/alerts/ledger-alerts.yaml` |

Dashboards and alert routing are deployment configuration, not process code:
`docs/observability/prometheus.yml`, `docs/observability/alerts/`, and
`docs/observability/ledger-overview.dashboard.json`.

## 2. Structured logs

`JsonLogSink` writes one line per event:

```json
{"attributes":{"port":8080,"tls_required":true},"context":{},"name":"ledger.service.started","service":"ledger","timestamp":"2026-09-11T21:00:00+00:00"}
```

The service process wires this sink in `create_app()` and in `python -m ledger`
when `LEDGER_TELEMETRY_ENABLED` is true. Every processing module emits its
assigned events (`ledger.ingestion.*`, `ledger.validation.*`,
`ledger.normalization.completed`, `ledger.identity.verified`,
`ledger.candidates.generated`, `ledger.reconciliation.completed`,
`ledger.resolution.applied`, `ledger.api.request`).

The process performs **no network I/O** for logs. A log shipper (Fluent Bit,
Vector, the platform's agent, or a container stdout collector) forwards stdout to
the log backend. Shipping is owned by the deployment (Epic 7); this repository
does not embed a backend SDK or credentials.

## 3. Metrics and bounded labels

`MetricsRegistry` accepts only registered metric names with an allowlisted label
set. An unlisted name or label raises `ObservabilityError` instead of silently
creating a new time series, so cardinality cannot grow with request data. Route
labels are normalized by `route_template()`: identifiers such as
`/v1/batches/abc:def/records` collapse to `/v1/batches/{id}/records`.

| Metric | Labels | Meaning |
| --- | --- | --- |
| `ledger_http_requests_total` | `method`, `route`, `status` | request outcome |
| `ledger_http_request_duration_seconds` | `method`, `route` | request latency histogram |
| `ledger_http_requests_in_flight` | — | current in-flight requests |
| `ledger_http_rejections_total` | `reason` | boundary rejections by cause |
| `ledger_db_failures_total` | `operation` | database failures |
| `ledger_processing_failures_total` | `stage` | pipeline stage failures |
| `ledger_processing_retries_total` | `stage` | retries |
| `ledger_audit_failures_total` | `operation` | audit write failures |
| `ledger_records_ingested_total` | `source_id`, `outcome` | ingest outcomes (`accepted`, `invalid`, `duplicate`) |
| `ledger_reconciliations_total` | `outcome` | the seven reconciliation outcomes |
| `ledger_alert_fired_total` | `alert` | alerts fired |
| `ledger_service_starts_total` | — | process starts |

Derived at scrape time (never stored): `ledger_service_up`,
`ledger_ready_state`, `ledger_http_server_error_ratio`,
`ledger_http_request_duration_seconds_p95`, `ledger_in_flight_ratio`,
`ledger_in_flight_limit`.

Domain counters are produced by `MetricsTelemetryBridge`: domain services keep
emitting `TelemetryEvent`s and know nothing about metrics. The bridge forwards
each event to the downstream sink and increments counters only for events with a
fixed outcome set (the reconciliation outcome enum and the three ingest
outcomes). `RECONCILIATION_OUTCOMES` mirrors the domain enum and a test asserts
they stay equal.

Backup freshness comes from the node exporter textfile collector, written by
`PYTHONPATH=src python3 -m ledger.ops backup ... --metrics-output <dir>/ledger-backup.prom`:
`ledger_backup_last_success_timestamp_seconds`, `ledger_backup_last_run_ok`,
`ledger_backup_bytes`, `ledger_backup_duration_seconds`. On a failed attempt the
success timestamp is preserved, so staleness keeps growing.

```sh
# Local scrape
PYTHONPATH=src LEDGER_API_TOKENS='dev-token:reconciliation_operator' python3 -m ledger &
curl -s http://127.0.0.1:8080/v1/metrics | head

# Regenerate the alert artifact after editing rule data
PYTHONPATH=src python3 -m ledger.alerts docs/observability/alerts/ledger-alerts.yaml
```

`/v1/metrics`, `/v1/health`, and `/v1/ready` are public probes. They expose no
business data; scrape them only from a trusted network.

## 4. Correlation

The service accepts `X-Correlation-ID`, generates one when absent, propagates it
to the API layer, echoes it as a response header, and includes it in every JSON
response body. Correlation ids connect a request to its log lines without
carrying business payloads. **Correlation ids are never used as metric labels** —
that would be unbounded cardinality.

## 5. Redaction and retention

`TelemetryEvent.as_dict()` runs every attribute mapping through `_redact`, which
replaces values whose key contains `password`, `secret`, `token`, `credential`,
`authorization`, `payload`, or `description` with `[REDACTED]`.

Never logged: raw record payloads and descriptions, canonical field values,
request bodies, bearer tokens, and authorization headers. Allowed: identifiers,
counts, outcomes, durations, versions, and status codes.

Retention (`TELEMETRY_RETENTION`, surfaced by `ledger.observability.retention_policy()`):

| Signal | Retention |
| --- | --- |
| Logs | 30 days in the log backend; the process keeps no history |
| Metrics | 15 months at 1 minute resolution |
| Traces | not enabled in v1.0 (correlation ids only) |
| Alerts | 90 days of state and notifications |

## 6. Dashboards and alerts

`docs/observability/ledger-overview.dashboard.json` is a Grafana dashboard
(service up/ready, request rate and error ratio, p95 latency, in-flight
saturation, database failures, processing failures and retries, audit failures,
reconciliation outcomes, backup age, alert firings).

`docs/observability/alerts/ledger-alerts.yaml` is **generated** from
`ALERT_RULES` in `src/ledger/alerts.py`; a test asserts the artifact matches the
rule data, so thresholds cannot drift. Ten rules cover availability, readiness,
database failure, audit failure, processing failure, retry storms, 5xx ratio,
latency, saturation, and backup staleness.

`evaluate_and_emit(AlertInputs(...))` is the in-process drill path: it evaluates
the same rules against aggregated inputs, increments `ledger_alert_fired_total`,
and emits `ledger.alert.fired`. `tests/test_observability.py` uses it to prove
each alert fires for its condition and stays silent otherwise.

Runbooks for every alert are in `docs/runbooks/`.

## 7. Local verification

```sh
make check                                       # includes tests/test_observability.py
PYTHONPATH=src python3 -m unittest tests.test_observability -v
```

## 8. Honest limitations

- **No hosted backend is provisioned by this repository.** The process emits
  stdout logs and a scrape endpoint; connecting a log backend, Prometheus,
  Alertmanager, and Grafana is deployment work owned by Epic 7 and rehearsed in
  Epic 8. Until then, "production events reach the selected backend" is proven
  only for the integration boundary (the JSON line and the scrape endpoint), not
  for a live third-party service.
- **The alertmanager receiver is a placeholder** (`alert-sink.invalid`). Routing
  credentials are supplied at deploy time and never committed.
- **Alerts are threshold-based**, not anomaly-based. Thresholds are explicit and
  deliberately few.
- **Traces are not enabled.** Correlation ids are the v1.0 mechanism; OpenTelemetry
  propagation is a future decision, not an undocumented behavior.
- **Latency thresholds are provisional** until the Epic 8 staging measurements
  establish the D-009 capacity baseline.
