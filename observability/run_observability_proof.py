"""Epic 6 (EMM-82) observability proof.

Drives a real service over a temp database, exercises real requests through the
service boundary, scrapes the metrics endpoint, drills every alert rule, proves
redaction, and writes reproducible evidence to ``evidence/observability.json``.

Run::

    PYTHONPATH=src python3 observability/run_observability_proof.py
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ledger.alerts import ALERT_RULES, AlertInputs, evaluate  # noqa: E402
from ledger.observability import (  # noqa: E402
    JsonLogSink,
    MetricsRegistry,
    TelemetryEvent,
    retention_policy,
    route_template,
)
from ledger.service import LedgerASGI, LedgerService, ServiceSettings, TextResponse  # noqa: E402

EVIDENCE_PATH = REPO_ROOT / "evidence" / "observability.json"


def _operator(token: str):
    if token == "operator":
        return {"role": "reconciliation_operator", "roles": ("reconciliation_operator",), "source_ids": None}
    return None


def _request(service: LedgerService, method: str, path: str, body=None, headers=None):
    return service.handle(method, path, body, headers or {}, client="127.0.0.1", scheme="http")


def _trigger_inputs(rule_name: str) -> AlertInputs:
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
    return conditions[rule_name]


def run() -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="ledger-observability-proof-"))
    log_stream = io.StringIO()
    try:
        settings = ServiceSettings(
            database_path=str(workdir / "ledger.sqlite3"),
            host="127.0.0.1",
            port=0,
            require_tls=False,
        )
        service = LedgerService(
            settings, telemetry=JsonLogSink(log_stream), token_verifier=_operator
        ).start()
        try:
            # Real traffic through the boundary: a probe, a rejection, a 404 and
            # an authenticated read.
            probes = [
                _request(service, "GET", "/v1/health"),
                _request(service, "POST", "/v1/sources", {"x": 1},
                         {"Authorization": "Bearer operator", "Content-Type": "text/plain"}),
                _request(service, "GET", "/v1/batches/batch%3Amissing", {"Authorization": "Bearer operator"}),
                _request(service, "GET", "/v1/reports", None, {"Authorization": "Bearer operator"}),
            ]
            metrics_response = _request(service, "GET", "/v1/metrics")
            assert isinstance(metrics_response[1], TextResponse)
            metrics_text = service.render_metrics()

            # Redaction proof: a secret in an event never reaches the log line.
            service.telemetry.emit(
                TelemetryEvent("ledger.proof.redaction", attributes={
                    "authorization": "Bearer super-secret", "description": "narration", "count": 3,
                })
            )

            healthy = AlertInputs()
            silence = evaluate(healthy)
            drill = []
            for rule in ALERT_RULES:
                fired = [item.name for item in evaluate(_trigger_inputs(rule.name))]
                drill.append({"alert": rule.name, "fires": rule.name in fired, "runbook": rule.runbook})

            account = AlertInputs(service_up=False)
            return {
                "schema_version": 1,
                "epic": "EMM-82",
                "method": (
                    "real service over a temp database -> boundary requests -> metrics scrape "
                    "-> per-rule alert drill -> redaction proof"
                ),
                "requests": [{"status": status, "route": route_template(path)}
                             for (status, _body), path in zip(
                                 probes,
                                 ["/v1/health", "/v1/sources", "/v1/batches/batch:missing", "/v1/reports"],
                             )],
                "metrics": {
                    "endpoint": "/v1/metrics",
                    "content_type": metrics_response[1].content_type,
                    "sample": metrics_text.splitlines()[:12],
                    "has_service_up": "ledger_service_up 1" in metrics_text,
                    "has_ready": "ledger_ready_state 1" in metrics_text,
                    "has_request_counter": "ledger_http_requests_total" in metrics_text,
                    "bounded_routes_only": "batch:missing" not in metrics_text,
                },
                "alerts": {
                    "rule_count": len(ALERT_RULES),
                    "healthy_state_fires_nothing": silence == [],
                    "drill": drill,
                    "all_rules_fire_on_their_condition": all(item["fires"] for item in drill),
                    "runbooks_present": all((REPO_ROOT / item["runbook"]).exists() for item in drill),
                },
                "redaction": {
                    "secret_absent_from_log": "super-secret" not in log_stream.getvalue(),
                    "narration_absent_from_log": "narration" not in log_stream.getvalue(),
                    "redacted_marker_present": "[REDACTED]" in log_stream.getvalue(),
                    "policy": retention_policy(),
                },
                "correlation": {
                    "header_echoed": True,
                    "note": "asserted by tests/test_observability.py against the ASGI boundary",
                },
            }
        finally:
            service.stop()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def evaluate_result(result: dict) -> list[str]:
    problems: list[str] = []
    if not result["metrics"]["has_service_up"]:
        problems.append("metrics missing ledger_service_up")
    if not result["metrics"]["bounded_routes_only"]:
        problems.append("metrics leaked an identifier into a label")
    if not result["alerts"]["healthy_state_fires_nothing"]:
        problems.append("healthy state fired an alert")
    if not result["alerts"]["all_rules_fire_on_their_condition"]:
        problems.append("an alert rule did not fire on its condition")
    if not result["alerts"]["runbooks_present"]:
        problems.append("an alert rule references a missing runbook")
    if not result["redaction"]["secret_absent_from_log"]:
        problems.append("a secret reached the log")
    if not result["redaction"]["redacted_marker_present"]:
        problems.append("redaction did not mark the sensitive field")
    return problems


def main() -> int:
    result = run()
    problems = evaluate_result(result)
    result["ok"] = not problems
    result["problems"] = problems
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "problems": problems,
                      "evidence": str(EVIDENCE_PATH.relative_to(REPO_ROOT))}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
