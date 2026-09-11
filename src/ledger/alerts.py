"""Alert rules as code, with a bounded evaluation surface.

Alerting is part of the observability boundary. Rules live here as data so the
Prometheus rule artifact and the in-process evaluator cannot drift: the YAML is
generated from ``ALERT_RULES`` and a test asserts they match.

Firing an alert only emits telemetry and increments a bounded counter. Nothing
here pages anyone by itself; the alert manager owns notification routing. An
alert is operational signal, never authoritative business state (Architecture §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .observability import CorrelationContext, MetricsRegistry, TelemetryEvent, TelemetrySink


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True, slots=True)
class AlertRule:
    """One alert condition over bounded, already-aggregated inputs."""

    name: str
    severity: str
    summary: str
    expr: str
    for_seconds: int
    runbook: str
    trigger: str
    description: str = ""

    def to_rule_yaml(self) -> str:
        description = self.description or self.summary
        lines = [
            f"      - alert: {self.name}",
            f"        expr: {self.expr}",
            f"        for: {self.for_seconds}s",
            "        labels:",
            f"          severity: {self.severity}",
            "        annotations:",
            f"          summary: {_yaml_scalar(self.summary)}",
            f"          description: {_yaml_scalar(description)}",
            f"          runbook: {_yaml_scalar(self.runbook)}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class AlertInputs:
    """Aggregated values an evaluation pass may consider."""

    service_up: bool = True
    ready: bool = True
    window_requests: int = 0
    server_error_ratio: float = 0.0
    latency_p95_seconds: float = 0.0
    in_flight: int = 0
    in_flight_limit: int = 64
    db_failures: int = 0
    processing_failures: int = 0
    retries: int = 0
    audit_failures: int = 0
    backup_stale_seconds: float = 0.0


# Thresholds are deliberately explicit and few. They are warning-level by default
# and become critical only for availability, data-integrity, and audit failures.
ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="LedgerServiceDown",
        severity="critical",
        summary="LEDGER service is not passing its liveness probe",
        expr="ledger_service_up == 0",
        for_seconds=60,
        runbook="docs/runbooks/service-down.md",
        trigger="not service_up",
        description="The process is not serving. Check the process supervisor and last structured log lines.",
    ),
    AlertRule(
        name="LedgerReadinessFailing",
        severity="critical",
        summary="LEDGER readiness probe is failing (database unreachable)",
        expr="ledger_ready_state == 0",
        for_seconds=60,
        runbook="docs/runbooks/database-unavailable.md",
        trigger="not ready",
        description="Liveness is up but the authoritative database cannot be reached; the service is not usable.",
    ),
    AlertRule(
        name="LedgerDatabaseFailures",
        severity="critical",
        summary="LEDGER database operation failures are occurring",
        expr="increase(ledger_db_failures_total[5m]) > 0",
        for_seconds=0,
        runbook="docs/runbooks/database-unavailable.md",
        trigger="db_failures > 0",
        description="Authoritative state may be unavailable. Verify integrity and restore from the last verified snapshot if needed.",
    ),
    AlertRule(
        name="LedgerAuditFailures",
        severity="critical",
        summary="LEDGER audit writes are failing",
        expr="increase(ledger_audit_failures_total[5m]) > 0",
        for_seconds=0,
        runbook="docs/runbooks/audit-failure.md",
        trigger="audit_failures > 0",
        description="An operation failed to record append-only audit history. This is an invariant-adjacent failure and must be investigated immediately.",
    ),
    AlertRule(
        name="LedgerProcessingFailures",
        severity="warning",
        summary="LEDGER reconciliation processing is failing",
        expr="increase(ledger_processing_failures_total[10m]) > 0",
        for_seconds=0,
        runbook="docs/runbooks/processing-failures.md",
        trigger="processing_failures > 0",
        description="A pipeline stage failed. Identify the stage label and batch, then re-run the idempotent operator from docs/service.md.",
    ),
    AlertRule(
        name="LedgerRetryStorm",
        severity="warning",
        summary="LEDGER is retrying processing repeatedly",
        expr="increase(ledger_processing_retries_total[10m]) > 10",
        for_seconds=0,
        runbook="docs/runbooks/processing-failures.md",
        trigger="retries > 10",
        description="A retry loop is in progress. Confirm the underlying failure rather than letting retries accumulate.",
    ),
    AlertRule(
        name="LedgerServerErrorRatio",
        severity="warning",
        summary="LEDGER HTTP 5xx ratio is elevated",
        expr="ledger_http_server_error_ratio > 0.02",
        for_seconds=300,
        runbook="docs/runbooks/high-error-rate.md",
        trigger="server_error_ratio > 0.02",
        description="More than 2% of requests in the window returned 5xx.",
    ),
    AlertRule(
        name="LedgerLatencyHigh",
        severity="warning",
        summary="LEDGER p95 request latency is above the approved objective",
        expr="ledger_http_request_duration_seconds_p95 > 1",
        for_seconds=600,
        runbook="docs/runbooks/high-latency.md",
        trigger="latency_p95_seconds > 1.0",
        description="Sustained p95 latency above one second. Compare against the staging capacity baseline before changing anything.",
    ),
    AlertRule(
        name="LedgerSaturation",
        severity="warning",
        summary="LEDGER in-flight requests are near the concurrency limit",
        expr="ledger_in_flight_ratio > 0.8",
        for_seconds=300,
        runbook="docs/runbooks/saturation.md",
        trigger="in_flight > 0.8 * in_flight_limit",
        description="The single-process service is saturating. Added load will queue in front of the request lock.",
    ),
    AlertRule(
        name="LedgerBackupStale",
        severity="critical",
        summary="LEDGER database backup is stale and the approved RPO is broken",
        expr="time() - ledger_backup_last_success_timestamp_seconds > 3600",
        for_seconds=0,
        runbook="docs/runbooks/backup-failure.md",
        trigger="backup_stale_seconds > 3600",
        description="No verified snapshot has succeeded within one hour — four times the approved 15-minute cadence (D-014). The RPO is no longer enforced.",
    ),
)

ALERT_RULE_NAMES = tuple(rule.name for rule in ALERT_RULES)


def evaluate(inputs: AlertInputs) -> list[AlertRule]:
    """Return the rules whose condition currently holds for the given inputs."""
    fired: list[AlertRule] = []
    for rule in ALERT_RULES:
        if rule.trigger == "not service_up" and not inputs.service_up:
            fired.append(rule)
        elif rule.trigger == "not ready" and not inputs.ready:
            fired.append(rule)
        elif rule.trigger == "db_failures > 0" and inputs.db_failures > 0:
            fired.append(rule)
        elif rule.trigger == "audit_failures > 0" and inputs.audit_failures > 0:
            fired.append(rule)
        elif rule.trigger == "processing_failures > 0" and inputs.processing_failures > 0:
            fired.append(rule)
        elif rule.trigger == "retries > 10" and inputs.retries > 10:
            fired.append(rule)
        elif rule.trigger == "server_error_ratio > 0.02" and inputs.server_error_ratio > 0.02:
            fired.append(rule)
        elif rule.trigger == "latency_p95_seconds > 1.0" and inputs.latency_p95_seconds > 1.0:
            fired.append(rule)
        elif rule.trigger == "in_flight > 0.8 * in_flight_limit" and (
            inputs.in_flight > 0.8 * max(inputs.in_flight_limit, 1)
        ):
            fired.append(rule)
        elif rule.trigger == "backup_stale_seconds > 3600" and inputs.backup_stale_seconds > 3600:
            fired.append(rule)
    return fired


def evaluate_and_emit(
    inputs: AlertInputs,
    *,
    metrics: MetricsRegistry | None = None,
    telemetry: TelemetrySink | None = None,
) -> list[str]:
    """Evaluate all rules, record the outcome, and return the fired rule names."""
    fired = evaluate(inputs)
    for rule in fired:
        if metrics is not None:
            metrics.increment("ledger_alert_fired_total", alert=rule.name)
        if telemetry is not None:
            telemetry.emit(
                TelemetryEvent(
                    "ledger.alert.fired",
                    CorrelationContext(),
                    {"alert": rule.name, "severity": rule.severity, "runbook": rule.runbook},
                )
            )
    return [rule.name for rule in fired]


def render_prometheus_rules() -> str:
    """Render the Prometheus alerting rule artifact from the rule data."""
    lines = [
        "# Generated from src/ledger/alerts.py — do not edit by hand.",
        "# Regenerate with: PYTHONPATH=src python3 -m ledger.alerts",
        "groups:",
        "  - name: ledger-service",
        "    rules:",
    ]
    lines.extend(rule.to_rule_yaml() for rule in ALERT_RULES)
    return "\n".join(lines) + "\n"


def main() -> int:  # pragma: no cover - CLI helper
    import sys
    from pathlib import Path

    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("docs/observability/alerts/ledger-alerts.yaml")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_prometheus_rules(), encoding="utf-8")
    print(f"wrote {target} ({len(ALERT_RULES)} rules)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
