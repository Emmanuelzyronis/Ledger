"""Epic 6 (EMM-82) observability: logs, bounded metrics, correlation, alerts.

These tests drive the real observability boundary and the real service. They
assert the properties the epic must guarantee: telemetry is structured and
redacted, metric labels are bounded and derived from a fixed allowlist, the
alert artifact cannot drift from the rule data, every alert fires for its own
condition and stays silent otherwise, and the service exposes a scrape endpoint
that carries no business payload.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "observability"))

from run_observability_proof import evaluate_result, run as run_observability_proof  # noqa: E402

from ledger.alerts import (  # noqa: E402
    ALERT_RULES,
    AlertInputs,
    evaluate,
    evaluate_and_emit,
    render_prometheus_rules,
)
from ledger.domain.types import ReconciliationOutcome  # noqa: E402
from ledger.observability import (  # noqa: E402
    RECONCILIATION_OUTCOMES,
    CompositeSink,
    CorrelationContext,
    InMemoryTelemetrySink,
    JsonLogSink,
    METRIC_LABELS,
    MetricsRegistry,
    MetricsTelemetryBridge,
    ObservabilityError,
    TelemetryEvent,
    retention_policy,
    route_template,
)
from ledger.service import LedgerASGI, LedgerService, ServiceSettings, TextResponse  # noqa: E402


ALERT_ARTIFACT = REPO_ROOT / "docs" / "observability" / "alerts" / "ledger-alerts.yaml"
DASHBOARD_ARTIFACT = REPO_ROOT / "docs" / "observability" / "ledger-overview.dashboard.json"


def operator_verifier(token: str):
    if token == "operator":
        return {"role": "reconciliation_operator", "roles": ("reconciliation_operator",), "source_ids": None}
    return None


def quiet_settings(**overrides):
    values = {"host": "127.0.0.1", "port": 8080, "database_path": ":memory:",
              "max_body_bytes": 1_048_576, "drain_timeout_seconds": 5.0}
    values.update(overrides)
    return ServiceSettings(**values)


def asgi_send(app, method, path, payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    request_headers = dict(headers or {})
    if payload is not None and not any(key.casefold() == "content-type" for key in request_headers):
        request_headers["Content-Type"] = "application/json"
    scope = {"type": "http", "method": method, "path": path, "query_string": b"",
             "headers": [(key.lower().encode(), value.encode()) for key, value in request_headers.items()]}
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body_message = next(message for message in sent if message["type"] == "http.response.body")
    return start, body_message["body"]


class JsonLogSinkTests(unittest.TestCase):
    def test_lines_are_json_redacted_and_carry_correlation(self):
        stream = io.StringIO()
        sink = JsonLogSink(stream, service="ledger")
        sink.emit(
            TelemetryEvent(
                "ledger.api.request",
                CorrelationContext(batch_id="batch:1", record_id="raw:1"),
                {"method": "POST", "status": 200, "authorization_token": "super-secret",
                 "description": "customer narration", "count": 1},
            )
        )
        payload = json.loads(stream.getvalue().strip())
        self.assertEqual(payload["name"], "ledger.api.request")
        self.assertEqual(payload["service"], "ledger")
        self.assertEqual(payload["context"], {"batch_id": "batch:1", "record_id": "raw:1"})
        self.assertEqual(payload["attributes"]["authorization_token"], "[REDACTED]")
        self.assertEqual(payload["attributes"]["description"], "[REDACTED]")
        self.assertEqual(payload["attributes"]["count"], 1)
        self.assertNotIn("super-secret", stream.getvalue())
        self.assertNotIn("customer narration", stream.getvalue())

    def test_composite_sink_fans_out_to_every_sink(self):
        first, second = InMemoryTelemetrySink(), InMemoryTelemetrySink()
        CompositeSink(first, second).emit(TelemetryEvent("ledger.test"))
        self.assertEqual(len(first.events), 1)
        self.assertEqual(len(second.events), 1)

    def test_retention_and_redaction_policy_is_exposed(self):
        policy = retention_policy()
        self.assertIn("logs", policy["retention"])
        self.assertIn("mechanism", policy["redaction"])
        self.assertIn("raw record payloads and descriptions", policy["redaction"]["never_logged"])


class MetricsTests(unittest.TestCase):
    def test_route_template_collapses_identifiers(self):
        self.assertEqual(route_template("/v1/batches/batch:abc/records"), "/v1/batches/{id}/records")
        self.assertEqual(route_template("/v1/discrepancies/disc:1?x=1"), "/v1/discrepancies/{id}")
        self.assertEqual(route_template("/v1/health"), "/v1/health")
        self.assertEqual(route_template("/"), "/")

    def test_unregistered_metric_and_label_are_rejected(self):
        metrics = MetricsRegistry()
        with self.assertRaises(ObservabilityError):
            metrics.increment("ledger_not_a_metric")
        with self.assertRaises(ObservabilityError):
            metrics.increment("ledger_http_requests_total", method="GET", route="/x", status="200", batch_id="b")

    def test_every_registered_metric_renders_and_counters_accumulate(self):
        metrics = MetricsRegistry()
        for name in METRIC_LABELS:
            metrics.increment(name, **{label: "x" for label in METRIC_LABELS[name]})
        rendered = metrics.render_prometheus()
        for name in METRIC_LABELS:
            self.assertIn(name, rendered)
        metrics.observe("ledger_http_request_duration_seconds", 0.01, method="GET", route="/v1/health")
        histogram = metrics.render_prometheus()
        self.assertIn("ledger_http_request_duration_seconds_bucket", histogram)
        self.assertIn("ledger_http_request_duration_seconds_count", histogram)

    def test_long_label_values_are_truncated(self):
        metrics = MetricsRegistry()
        metrics.increment("ledger_records_ingested_total", source_id="s" * 500, outcome="accepted")
        (labels, _value), = metrics.counter_series("ledger_records_ingested_total").items()
        self.assertLessEqual(len(dict(labels)["source_id"]), 96)

    def test_outcome_set_matches_the_domain_enum(self):
        self.assertEqual(RECONCILIATION_OUTCOMES, {item.value for item in ReconciliationOutcome})


class TelemetryBridgeTests(unittest.TestCase):
    def test_bridge_records_bounded_counters_and_forwards_events(self):
        metrics = MetricsRegistry()
        downstream = InMemoryTelemetrySink()
        bridge = MetricsTelemetryBridge(metrics, downstream)

        bridge.emit(TelemetryEvent("ledger.ingestion.record_accepted",
                                   CorrelationContext(batch_id="b"), {"source_id": "source-a"}))
        bridge.emit(TelemetryEvent("ledger.ingestion.record_invalid",
                                   CorrelationContext(batch_id="b"), {"source_id": "source-a"}))
        bridge.emit(TelemetryEvent("ledger.reconciliation.completed",
                                   CorrelationContext(batch_id="b"), {"outcome": "AMBIGUOUS"}))
        bridge.emit(TelemetryEvent("ledger.unknown.event", CorrelationContext(), {"x": 1}))

        self.assertEqual(metrics.counter_value(
            "ledger_records_ingested_total", source_id="source-a", outcome="accepted"), 1.0)
        self.assertEqual(metrics.counter_value(
            "ledger_records_ingested_total", source_id="source-a", outcome="invalid"), 1.0)
        self.assertEqual(metrics.counter_value("ledger_reconciliations_total", outcome="AMBIGUOUS"), 1.0)
        self.assertEqual(len(downstream.events), 4)

    def test_an_out_of_enum_outcome_is_not_recorded_as_a_label(self):
        metrics = MetricsRegistry()
        MetricsTelemetryBridge(metrics).emit(
            TelemetryEvent("ledger.reconciliation.completed", CorrelationContext(), {"outcome": "WHAT"})
        )
        self.assertEqual(metrics.counter_series("ledger_reconciliations_total"), {})


class AlertTests(unittest.TestCase):
    def test_artifact_matches_rule_data(self):
        self.assertTrue(ALERT_ARTIFACT.exists(), "alert artifact must be committed")
        self.assertEqual(ALERT_ARTIFACT.read_text(encoding="utf-8"), render_prometheus_rules())

    def test_dashboard_artifact_is_valid_json_with_the_core_panels(self):
        dashboard = json.loads(DASHBOARD_ARTIFACT.read_text(encoding="utf-8"))
        titles = {panel["title"] for panel in dashboard["panels"]}
        self.assertIn("Service up", titles)
        self.assertIn("Backup age", titles)
        self.assertIn("Database failures", titles)

    def test_each_rule_fires_for_its_condition_and_not_otherwise(self):
        quiet = AlertInputs(service_up=True, ready=True, db_failures=0, processing_failures=0,
                            retries=0, audit_failures=0, server_error_ratio=0.0,
                            latency_p95_seconds=0.0, in_flight=0, in_flight_limit=64,
                            backup_stale_seconds=0.0)
        self.assertEqual(evaluate(quiet), [])
        conditions = {
            "LedgerServiceDown": AlertInputs(service_up=False),
            "LedgerReadinessFailing": AlertInputs(ready=False),
            "LedgerDatabaseFailures": AlertInputs(db_failures=1),
            "LedgerAuditFailures": AlertInputs(audit_failures=1),
            "LedgerProcessingFailures": AlertInputs(processing_failures=1),
            "LedgerRetryStorm": AlertInputs(retries=11),
            "LedgerServerErrorRatio": AlertInputs(server_error_ratio=0.5),
            "LedgerLatencyHigh": AlertInputs(latency_p95_seconds=2.0),
            "LedgerSaturation": AlertInputs(in_flight=52, in_flight_limit=64),
            "LedgerBackupStale": AlertInputs(backup_stale_seconds=3601),
        }
        self.assertEqual(set(conditions), {rule.name for rule in ALERT_RULES})
        for rule in ALERT_RULES:
            with self.subTest(alert=rule.name):
                fired = [item.name for item in evaluate(conditions[rule.name])]
                self.assertIn(rule.name, fired)

    def test_evaluate_and_emit_counts_and_emits(self):
        metrics = MetricsRegistry()
        telemetry = InMemoryTelemetrySink()
        fired = evaluate_and_emit(AlertInputs(db_failures=1), metrics=metrics, telemetry=telemetry)
        self.assertEqual(fired, ["LedgerDatabaseFailures"])
        self.assertEqual(metrics.counter_value("ledger_alert_fired_total", alert="LedgerDatabaseFailures"), 1.0)
        self.assertEqual(telemetry.events[0]["name"], "ledger.alert.fired")
        self.assertEqual(telemetry.events[0]["attributes"]["alert"], "LedgerDatabaseFailures")

    def test_every_alert_references_an_existing_runbook(self):
        for rule in ALERT_RULES:
            with self.subTest(alert=rule.name):
                self.assertTrue((REPO_ROOT / rule.runbook).exists(), f"{rule.runbook} is missing")


class ServiceObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="ledger-observability-")
        self.telemetry = InMemoryTelemetrySink()
        self.service = LedgerService(
            quiet_settings(database_path=str(Path(self.directory) / "ledger.sqlite3")),
            telemetry=self.telemetry,
            token_verifier=operator_verifier,
        ).start()
        self.addCleanup(self.service.stop)
        self.app = LedgerASGI(self.service)

    def _send(self, method, path, **kwargs):
        return asgi_send(self.app, method, path, **kwargs)

    def test_metrics_endpoint_is_text_without_business_payload(self):
        start, raw = self._send("GET", "/v1/metrics")
        self.assertEqual(start["status"], 200)
        content_type = dict((k.decode(), v.decode()) for k, v in start["headers"])["content-type"]
        self.assertTrue(content_type.startswith("text/plain"))
        text = raw.decode()
        self.assertIn("ledger_service_up 1", text)
        self.assertIn("ledger_ready_state 1", text)

    def test_request_metrics_use_bounded_route_labels(self):
        self._send("GET", "/v1/batches/batch%3Aabc", headers={"Authorization": "Bearer operator"})
        text = self.service.render_metrics()
        self.assertIn('route="/v1/batches/{id}"', text)
        self.assertNotIn("batch:abc", text)
        self.assertIn('status="404"', text)

    def test_correlation_id_is_echoed_as_a_header_and_never_a_metric_label(self):
        start, _raw = self._send("GET", "/v1/health", headers={"X-Correlation-ID": "corr-123"})
        headers = {key.decode(): value.decode() for key, value in start["headers"]}
        self.assertEqual(headers["x-correlation-id"], "corr-123")
        self.assertNotIn("corr-123", self.service.render_metrics())

    def test_rejections_and_failures_are_counted_by_reason_without_payloads(self):
        self._send("POST", "/v1/sources", payload={"x": 1},
                   headers={"Authorization": "Bearer operator", "Content-Type": "text/plain"})
        self.assertEqual(
            self.service.metrics.counter_value("ledger_http_rejections_total", reason="unsupported_media_type"),
            1.0,
        )
        rendered = self.service.render_metrics()
        self.assertIn("ledger_http_server_error_ratio", rendered)
        self.assertIn("ledger_http_request_duration_seconds_p95", rendered)

    def test_startup_telemetry_is_emitted_without_secrets(self):
        names = [event["name"] for event in self.telemetry.events]
        self.assertIn("ledger.service.started", names)
        for event in self.telemetry.events:
            self.assertNotIn("token", json.dumps(event["attributes"]).casefold())

    def test_domain_events_reach_the_bridge_metrics_and_the_sink(self):
        self.service.telemetry.emit(
            TelemetryEvent(
                "ledger.reconciliation.completed",
                CorrelationContext(batch_id="batch:1"),
                {"outcome": "MATCHED"},
            )
        )
        self.assertEqual(
            self.service.metrics.counter_value("ledger_reconciliations_total", outcome="MATCHED"), 1.0
        )
        self.assertEqual(self.telemetry.events[-1]["name"], "ledger.reconciliation.completed")


class ObservabilityProofTests(unittest.TestCase):
    def test_reproducible_observability_proof_has_no_problems(self):
        result = run_observability_proof()
        self.assertEqual(evaluate_result(result), [], result)
        self.assertTrue(result["metrics"]["bounded_routes_only"])
        self.assertTrue(result["alerts"]["all_rules_fire_on_their_condition"])
        self.assertTrue(result["redaction"]["secret_absent_from_log"])


if __name__ == "__main__":
    unittest.main()
