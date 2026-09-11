"""Foundation telemetry interfaces with correlation and redaction safeguards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


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
