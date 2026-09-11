"""Layer 6 deterministic normalization of validated raw records."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import unicodedata
from collections.abc import Mapping
from typing import Any

from .domain import AuditEvent, AuditEventType, BatchCounters, CanonicalTransaction, Direction
from .identity import audit_event_identity, canonical_fingerprint, canonical_identity
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


_FIELDS = {
    "source_a.v1": {"record_id": "record_id", "occurred_at": "occurred_at", "amount": "amount", "currency": "currency", "direction": "direction", "account_reference": "account_reference", "transaction_reference": "transaction_reference", "description": "description", "transaction_type": "transaction_type"},
    "source_b.v1": {"id": "record_id", "posted": "occurred_at", "value": "amount", "ccy": "currency", "side": "direction", "account_ref": "account_reference", "reference": "transaction_reference", "memo": "description", "type": "transaction_type"},
}


class NormalizationService:
    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None, actor: str = "system", normalization_version: str = "canonical_v2", validation_version: str = "validation_v1") -> None:
        self.database, self.telemetry, self.actor = database, telemetry, actor
        self.normalization_version, self.validation_version = normalization_version, validation_version

    def normalize_record(self, raw_record_id: str, *, created_at: datetime | None = None) -> CanonicalTransaction | None:
        raw = self.database.raw_records.get(raw_record_id)
        if raw is None:
            raise ValueError("raw record does not exist")
        existing = self.database.canonical_transactions.get_for_raw_version(raw_record_id, self.normalization_version)
        if existing is not None:
            return existing
        validation = self.database.validation_results.get_for_raw(raw_record_id, self.validation_version)
        if validation is None:
            raise ValueError("raw record has not been validated")
        if validation.status != "VALID":
            self._record_failure(raw, "validation_invalid", count_failure=False)
            return None
        try:
            fields = self._map(raw.schema_version, raw.payload)
            canonical_version = len(self.database.canonical_transactions.list_for_raw(raw_record_id)) + 1
            canonical_id = canonical_identity(raw.raw_record_id, self.normalization_version, canonical_version)
            prior = self.database.canonical_transactions.list_for_raw(raw_record_id)
            transaction = CanonicalTransaction(canonical_id, raw.source_id, raw.raw_record_id, raw.source_record_id,
                fields["occurred_at"], fields["amount"], fields["currency"], fields["direction"], self.normalization_version,
                canonical_version, "0" * 64, created_at or datetime.now(timezone.utc), fields.get("transaction_type"),
                fields.get("account_reference"), fields.get("transaction_reference"), fields.get("description"), fields.get("transaction_status"),
                prior[-1].canonical_id if prior else None)
            transaction = CanonicalTransaction(transaction.canonical_id, transaction.source_id, transaction.raw_record_id, transaction.source_record_id,
                transaction.occurred_at, transaction.amount, transaction.currency, transaction.direction, transaction.normalization_version,
                transaction.canonical_version, canonical_fingerprint(transaction), transaction.created_at, transaction.transaction_type,
                transaction.account_reference, transaction.transaction_reference, transaction.description, transaction.transaction_status,
                transaction.supersedes_canonical_id)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            self._record_failure(raw, self._failure_code(exc))
            return None
        with self.database.transaction():
            concurrent = self.database.canonical_transactions.get_for_raw_version(raw_record_id, self.normalization_version)
            if concurrent is not None:
                return concurrent
            self.database.canonical_transactions.save(transaction)
            self.database.audit_events.append(self._event(raw, AuditEventType.NORMALIZATION_COMPLETED, transaction.canonical_id, {"outcome": "SUCCESS", "canonical_transaction_id": transaction.canonical_id, "normalization_version": self.normalization_version}, record_id=raw_record_id))
        self._emit(raw, "SUCCESS", transaction.canonical_id)
        return transaction

    def _map(self, schema: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if schema not in _FIELDS:
            raise ValueError("unsupported_schema")
        source = _FIELDS[schema]
        values = {canonical: payload[key] for key, canonical in source.items() if key in payload}
        values["occurred_at"] = self._date(values["occurred_at"])
        values["amount"] = Decimal(str(values["amount"])).quantize(Decimal("0.0001"))
        values["currency"] = values["currency"].upper()
        values["direction"] = Direction(values["direction"])
        for key in ("transaction_type", "account_reference", "transaction_reference", "description", "transaction_status"):
            if key in values and values[key] is not None:
                values[key] = unicodedata.normalize("NFC", values[key]).strip()
        return values

    @staticmethod
    def _date(value: str) -> datetime:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), time(), tzinfo=timezone.utc)
        return datetime.fromisoformat(value).astimezone(timezone.utc)

    def _record_failure(self, raw: Any, code: str, *, count_failure: bool = True) -> None:
        event = self._event(raw, AuditEventType.NORMALIZATION_COMPLETED, raw.raw_record_id, {"outcome": "FAILED", "failure_code": code, "normalization_version": self.normalization_version}, record_id=raw.raw_record_id)
        with self.database.transaction():
            if self.database.audit_events.get(event.event_id) is not None:
                return
            if count_failure:
                batch = self.database.batches.get(raw.batch_id)
                if batch is None:
                    raise ValueError("batch does not exist")
                c = batch.counters
                self.database.batches.update_counters(raw.batch_id, BatchCounters(received_count=c.received_count, accepted_count=c.accepted_count, rejected_input_count=c.rejected_input_count, invalid_count=c.invalid_count, processed_count=c.processed_count, matched_count=c.matched_count, mismatched_count=c.mismatched_count, unmatched_count=c.unmatched_count, ambiguous_count=c.ambiguous_count, duplicate_count=c.duplicate_count, failed_count=c.failed_count + 1))
            self.database.audit_events.append(event)
        self._emit(raw, "FAILED", None, code)

    def _event(self, raw: Any, kind: AuditEventType, entity_id: str, metadata: dict[str, Any], *, record_id: str) -> AuditEvent:
        entity_type = "canonical_transaction" if entity_id != raw.raw_record_id else "raw_record"
        event_id = audit_event_identity(kind.value, entity_type, entity_id, None, self.normalization_version, 1)
        return AuditEvent(event_id, entity_type, entity_id, kind, self.actor, datetime.now(timezone.utc), 1, self.normalization_version, metadata, batch_id=raw.batch_id, record_id=record_id)

    def _emit(self, raw: Any, outcome: str, canonical_id: str | None, failure_code: str | None = None) -> None:
        if self.telemetry:
            attrs = {"source_id": raw.source_id, "schema_version": raw.schema_version, "normalization_version": self.normalization_version, "outcome": outcome}
            if canonical_id: attrs["canonical_transaction_id"] = canonical_id
            if failure_code: attrs["failure_code"] = failure_code
            self.telemetry.emit(TelemetryEvent("ledger.normalization.completed", CorrelationContext(batch_id=raw.batch_id, record_id=raw.raw_record_id), attrs))

    @staticmethod
    def _failure_code(exc: Exception) -> str:
        if isinstance(exc, KeyError):
            return "missing_field"
        if isinstance(exc, ArithmeticError):
            return "invalid_amount"
        if isinstance(exc, TypeError):
            return "invalid_field_type"
        if isinstance(exc, ValueError):
            message = str(exc)
            if "schema" in message:
                return "unsupported_schema"
            if "direction" in message:
                return "invalid_direction"
            if "currency" in message:
                return "invalid_currency"
            if "fromisoformat" in message or "day is out of range" in message:
                return "invalid_date"
            return "invalid_value"
        return "normalization_error"


Normalization = NormalizationService
