"""Layer 7 deterministic identities for source, raw, and canonical records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from .domain import CanonicalTransaction
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_json(value: Any) -> bytes:
    """Return the architecture's UTF-8, sorted-key canonical JSON encoding."""

    return json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_identity(source_id: str, source_record_id: str) -> str:
    return f"src:{source_id}:{source_record_id}"


def raw_fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json(payload))


def raw_identity(source_id: str, schema_version: str, payload_or_fingerprint: Mapping[str, Any] | str) -> str:
    fingerprint = payload_or_fingerprint if isinstance(payload_or_fingerprint, str) else raw_fingerprint(payload_or_fingerprint)
    return f"raw:{source_id}:{schema_version}:{fingerprint}"


def canonical_identity(raw_record_id: str, normalization_version: str, canonical_version: int) -> str:
    return f"can:{raw_record_id}:{normalization_version}:{canonical_version}"


def canonical_serialization(transaction: CanonicalTransaction) -> bytes:
    return canonical_json(transaction.semantic_payload())


def canonical_fingerprint(transaction: CanonicalTransaction) -> str:
    return sha256_hex(canonical_serialization(transaction))


def audit_event_identity(event_type: str, entity_type: str, entity_id: str, attempt_id: str | None, stage_version: str, sequence: int) -> str:
    logical_key = [event_type, entity_type, entity_id, attempt_id, stage_version, sequence]
    return "audit:" + sha256_hex(canonical_json(logical_key))


@dataclass(frozen=True, slots=True)
class TransactionIdentity:
    source_identity: str
    raw_identity: str
    canonical_identity: str
    canonical_fingerprint: str
    normalization_version: str
    canonical_version: int


class IdentityService:
    """Verifies and exposes identities already authoritative on canonical rows."""

    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None) -> None:
        self.database, self.telemetry = database, telemetry

    def identify(self, canonical_transaction_id: str | CanonicalTransaction, *, attempt_id: str | None = None) -> TransactionIdentity:
        transaction = (self.database.canonical_transactions.get(canonical_transaction_id)
                       if isinstance(canonical_transaction_id, str) else canonical_transaction_id)
        if transaction is None:
            raise ValueError("canonical transaction does not exist")
        expected_id = canonical_identity(transaction.raw_record_id, transaction.normalization_version, transaction.canonical_version)
        expected_fingerprint = canonical_fingerprint(transaction)
        if transaction.canonical_id != expected_id:
            raise ValueError("canonical identity does not match its lineage")
        if transaction.canonical_fingerprint != expected_fingerprint:
            raise ValueError("canonical fingerprint does not match semantic fields")
        result = TransactionIdentity(
            source_identity(transaction.source_id, transaction.source_record_id),
            transaction.raw_record_id,
            transaction.canonical_id,
            transaction.canonical_fingerprint,
            transaction.normalization_version,
            transaction.canonical_version,
        )
        if self.telemetry:
            raw = self.database.raw_records.get(transaction.raw_record_id)
            self.telemetry.emit(TelemetryEvent("ledger.identity.verified", CorrelationContext(
                batch_id=raw.batch_id if raw else None, attempt_id=attempt_id, record_id=transaction.raw_record_id
            ), {"canonical_transaction_id": transaction.canonical_id, "normalization_version": transaction.normalization_version,
                "canonical_version": transaction.canonical_version, "outcome": "VERIFIED"}))
        return result


Identity = IdentityService
