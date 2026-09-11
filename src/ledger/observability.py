"""Observability: telemetry interfaces, redaction, structured logs, and metrics.

This module owns the observability boundary. Domain and infrastructure code emit
``TelemetryEvent`` objects through a ``TelemetrySink``; this module guarantees the
two things that boundary must never get wrong:

* **Redaction** — sensitive keys are replaced before an event leaves the process.
* **Bounded labels** — metric label names come from a fixed allowlist and route
  labels are normalized, so metric cardinality cannot grow with request data.

Telemetry is *never* authoritative business state (Architecture §4).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import sys
import threading
import time
from typing import Any, Protocol, TextIO


CORRELATION_FIELDS = ("batch_id", "attempt_id", "record_id", "reconciliation_id")
_SENSITIVE_TERMS = (
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "payload",
    "description",
)


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Identifiers used to connect operational events without carrying business payloads."""

    batch_id: str | None = None
    attempt_id: str | None = None
    record_id: str | None = None
    reconciliation_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "batch_id": self.batch_id,
                "attempt_id": self.attempt_id,
                "record_id": self.record_id,
                "reconciliation_id": self.reconciliation_id,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Structured event shape shared by later processing layers."""

    name: str
    context: CorrelationContext = field(default_factory=CorrelationContext)
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "context": self.context.as_dict(),
            "attributes": _redact(self.attributes),
        }


class TelemetrySink(Protocol):
    """Output boundary implemented by infrastructure in a later layer."""

    def emit(self, event: TelemetryEvent) -> None:
        ...


class InMemoryTelemetrySink:
    """Small deterministic sink for foundation tests and local development."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event.as_dict())


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold()
    return any(term in normalized for term in _SENSITIVE_TERMS)


# --------------------------------------------------------------------------
# Structured logging
# --------------------------------------------------------------------------


class JsonLogSink:
    """Emit one redacted JSON object per line to a stream (stdout by default).

    The line-oriented shape is the contract a log shipper consumes. Nothing here
    performs network I/O, so the process never blocks on a backend and no
    credentials are needed at this boundary.
    """

    def __init__(self, stream: TextIO | None = None, *, service: str = "ledger") -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._service = service
        self._lock = threading.Lock()

    def emit(self, event: TelemetryEvent) -> None:
        payload = event.as_dict()
        payload["service"] = self._service
        line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


class CompositeSink:
    """Fan one event out to several sinks; ordering is deterministic."""

    def __init__(self, *sinks: TelemetrySink) -> None:
        self._sinks = tuple(sinks)

    def emit(self, event: TelemetryEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


# --------------------------------------------------------------------------
# Metrics with bounded labels
# --------------------------------------------------------------------------


class ObservabilityError(RuntimeError):
    """Raised when a metric violates the bounded-label contract."""


LATENCY_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

# Every metric and the *only* label names it may carry. Adding a label here is a
# deliberate observability change; an unlisted label raises instead of silently
# exploding cardinality.
METRIC_LABELS: dict[str, frozenset[str]] = {
    "ledger_http_requests_total": frozenset({"method", "route", "status"}),
    "ledger_http_request_duration_seconds": frozenset({"method", "route"}),
    "ledger_http_requests_in_flight": frozenset(),
    "ledger_http_rejections_total": frozenset({"reason"}),
    "ledger_db_failures_total": frozenset({"operation"}),
    "ledger_processing_failures_total": frozenset({"stage"}),
    "ledger_processing_retries_total": frozenset({"stage"}),
    "ledger_audit_failures_total": frozenset({"operation"}),
    "ledger_records_ingested_total": frozenset({"source_id", "outcome"}),
    "ledger_reconciliations_total": frozenset({"outcome"}),
    "ledger_alert_fired_total": frozenset({"alert"}),
    "ledger_service_starts_total": frozenset(),
}

# Mirrors the seven members of ``ledger.domain.types.ReconciliationOutcome``.
# A test asserts the two stay equal, so an outcome can never become an
# unbounded metric label silently.
RECONCILIATION_OUTCOMES = frozenset(
    {
        "MATCHED",
        "MISMATCHED",
        "UNMATCHED_A",
        "UNMATCHED_B",
        "AMBIGUOUS",
        "DUPLICATE",
        "INVALID",
    }
)


class MetricsTelemetryBridge:
    """Turn domain telemetry events into bounded metric series.

    Domain services emit events through a ``TelemetrySink`` and stay unaware of
    metrics. This sink forwards each event unchanged to the downstream sink and
    additionally increments the registered counters for events with a fixed
    outcome set. Unknown events are forwarded untouched.
    """

    _INGEST_EVENTS = {
        "ledger.ingestion.record_accepted": "accepted",
        "ledger.ingestion.record_invalid": "invalid",
        "ledger.ingestion.submission_duplicate": "duplicate",
    }

    def __init__(self, metrics: MetricsRegistry, downstream: TelemetrySink | None = None) -> None:
        self._metrics = metrics
        self._downstream = downstream

    def emit(self, event: TelemetryEvent) -> None:
        self._record(event)
        if self._downstream is not None:
            self._downstream.emit(event)

    def _record(self, event: TelemetryEvent) -> None:
        attributes = event.attributes
        if event.name == "ledger.reconciliation.completed":
            outcome = attributes.get("outcome")
            if outcome in RECONCILIATION_OUTCOMES:
                self._metrics.increment("ledger_reconciliations_total", outcome=outcome)
            return
        ingest_outcome = self._INGEST_EVENTS.get(event.name)
        if ingest_outcome is not None:
            self._metrics.increment(
                "ledger_records_ingested_total",
                source_id=attributes.get("source_id", "unknown"),
                outcome=ingest_outcome,
            )

# Only characters that would break the Prometheus text exposition format are
# replaced; route templates stay readable (`/v1/batches/{id}`).
_LABEL_VALUE = re.compile(r'[\\"\n\r\t]')
MAX_LABEL_VALUE = 96

# Route keywords that stay literal in a metric label; anything else that looks
# like an identifier is collapsed to a placeholder so ids never become labels.
_ROUTE_LITERALS = frozenset(
    {
        "v1",
        "health",
        "ready",
        "metrics",
        "batches",
        "records",
        "sources",
        "reports",
        "reconciliations",
        "discrepancies",
        "audit",
        "export",
        "resolve",
    }
)


def route_template(path: str) -> str:
    """Collapse a request path to a bounded, id-free route label."""
    raw_path = path.split("?", 1)[0]
    segments = [segment for segment in raw_path.strip("/").split("/") if segment]
    rendered = [segment if segment in _ROUTE_LITERALS else "{id}" for segment in segments]
    return "/" + "/".join(rendered) if rendered else "/"


def _sanitize_label(value: Any) -> str:
    text = str(value)
    if len(text) > MAX_LABEL_VALUE:
        text = text[:MAX_LABEL_VALUE]
    return _LABEL_VALUE.sub("_", text)


class MetricsRegistry:
    """Thread-safe counter/histogram registry with an allowlisted label set."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    # -- recording -----------------------------------------------------
    def increment(self, name: str, amount: float = 1.0, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += amount

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def set_gauge(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def _key(self, name: str, labels: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
        allowed = METRIC_LABELS.get(name)
        if allowed is None:
            raise ObservabilityError(f"metric {name!r} is not registered")
        unknown = set(labels) - allowed
        if unknown:
            raise ObservabilityError(
                f"metric {name!r} rejected unlisted labels {sorted(unknown)}; "
                "add them to METRIC_LABELS deliberately"
            )
        normalized = tuple(sorted((key, _sanitize_label(value)) for key, value in labels.items()))
        return name, normalized

    # -- reading -------------------------------------------------------
    def counter_value(self, name: str, **labels: Any) -> float:
        return self._counters.get(self._key(name, labels), 0.0)

    def histogram_values(self, name: str, **labels: Any) -> list[float]:
        return list(self._histograms.get(self._key(name, labels), ()))

    def counter_series(self, name: str) -> dict[tuple[tuple[str, str], ...], float]:
        """All label sets recorded for one counter, for derived ratios."""
        with self._lock:
            return {
                labels: value
                for (metric, labels), value in self._counters.items()
                if metric == name
            }

    def histogram_series(self, name: str) -> dict[tuple[tuple[str, str], ...], list[float]]:
        with self._lock:
            return {
                labels: list(values)
                for (metric, labels), values in self._histograms.items()
                if metric == name
            }

    def render_prometheus(self) -> str:
        """Render the registry in Prometheus text exposition format."""
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_render_labels(labels)} {_number(value)}")
            for (name, labels), values in sorted(self._histograms.items()):
                ordered = sorted(values)
                cumulative = 0
                bucket_lines = []
                for bucket in LATENCY_BUCKETS:
                    cumulative = sum(1 for item in ordered if item <= bucket)
                    bucket_lines.append(
                        f"{name}_bucket{_render_labels(labels, ('le', _number(bucket)))} {cumulative}"
                    )
                bucket_lines.append(
                    f"{name}_bucket{_render_labels(labels, ('le', '+Inf'))} {len(ordered)}"
                )
                lines.extend(bucket_lines)
                total = sum(ordered)
                suffix = f"_sum{_render_labels(labels)}"
                lines.append(f"{name}{suffix} {_number(total)}")
                lines.append(f"{name}_count{_render_labels(labels)} {len(ordered)}")
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(f"{name}{_render_labels(labels)} {_number(value)}")
        return "\n".join(lines) + "\n" if lines else ""


def _render_labels(labels: tuple[tuple[str, str], ...], extra: tuple[str, str] | None = None) -> str:
    items = list(labels)
    if extra is not None:
        items.append(extra)
    if not items:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in items)
    return "{" + rendered + "}"


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


# --------------------------------------------------------------------------
# Retention and redaction policy
# --------------------------------------------------------------------------


TELEMETRY_RETENTION = {
    "logs": "30 days in the log backend; the process keeps no log history",
    "metrics": "15 months in the metrics backend at 1 minute resolution",
    "traces": "not enabled in v1.0 (correlation ids only)",
    "alerts": "alert state and notifications retained 90 days by the alert manager",
}

REDACTION_POLICY = {
    "mechanism": "TelemetryEvent.as_dict applies _redact to every attributes mapping",
    "sensitive_terms": list(_SENSITIVE_TERMS),
    "never_logged": [
        "raw record payloads and descriptions",
        "canonical transaction field values",
        "bearer tokens, secrets, and authorization headers",
        "request bodies",
    ],
    "allowed": ["identifiers", "counts", "outcomes", "durations", "versions", "status codes"],
    "note": "Correlation ids are identifiers, not payloads, and are safe to log.",
}


def retention_policy() -> dict[str, Any]:
    return {"retention": dict(TELEMETRY_RETENTION), "redaction": dict(REDACTION_POLICY)}
