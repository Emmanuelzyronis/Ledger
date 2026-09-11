"""Layer 5 validation of immutable raw records."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re
from collections.abc import Mapping
from typing import Any

from .domain import AuditEvent, AuditEventType, BatchCounters, BatchState, ValidationResult
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


_AMOUNT = re.compile(r"^[+-]?(?:0|[1-9]\d*)(?:\.\d{1,4})?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCHEMAS = {
    "source_a.v1": {"record_id": "record_id", "occurred_at": "occurred_at", "amount": "amount", "currency": "currency", "direction": "direction", "account_reference": "account_reference", "transaction_reference": "transaction_reference", "description": "description", "transaction_type": "transaction_type"},
    "source_b.v1": {"id": "record_id", "posted": "occurred_at", "value": "amount", "ccy": "currency", "side": "direction", "account_ref": "account_reference", "reference": "transaction_reference", "memo": "description", "type": "transaction_type"},
}
_REQUIRED = {"record_id", "occurred_at", "amount", "currency", "direction"}


class ValidationService:
    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None, actor: str = "system", validation_version: str = "validation_v1") -> None:
        self.database, self.telemetry, self.actor, self.validation_version = database, telemetry, actor, validation_version

    def validate_record(self, raw_record_id: str, *, validated_at: datetime | None = None) -> ValidationResult:
        raw = self.database.raw_records.get(raw_record_id)
        if raw is None:
            raise ValueError("raw record does not exist")
        prior = self.database.validation_results.get_for_raw(raw_record_id, self.validation_version)
        if prior is not None:
            return prior
        errors = self._errors(raw.schema_version, raw.payload)
        result_id = "validation:" + hashlib.sha256(f"{raw_record_id}:{self.validation_version}".encode()).hexdigest()
        result = ValidationResult(result_id, raw.raw_record_id, raw.batch_id, raw.schema_version, self.validation_version, "INVALID" if errors else "VALID", tuple(errors), validated_at or datetime.now(timezone.utc))
        with self.database.transaction():
            existing = self.database.validation_results.get_for_raw(raw_record_id, self.validation_version)
            if existing is not None:
                return existing
            self.database.validation_results.save(result)
            batch = self.database.batches.get(raw.batch_id)
            if batch is None:
                raise ValueError("batch does not exist")
            counters = batch.counters
            newly_invalid = result.status == "INVALID" and raw.invalid_reason is None
            counters = BatchCounters(received_count=counters.received_count, accepted_count=counters.accepted_count, rejected_input_count=counters.rejected_input_count,
                invalid_count=counters.invalid_count + newly_invalid, processed_count=counters.processed_count + newly_invalid,
                matched_count=counters.matched_count, mismatched_count=counters.mismatched_count, unmatched_count=counters.unmatched_count,
                ambiguous_count=counters.ambiguous_count, duplicate_count=counters.duplicate_count, failed_count=counters.failed_count)
            self.database.batches.update_counters(batch.batch_id, counters)
            digest = hashlib.sha256(f"RECORD_VALIDATED:{raw.batch_id}:{raw.raw_record_id}:{self.validation_version}".encode()).hexdigest()
            self.database.audit_events.append(AuditEvent("audit:" + digest, "batch", batch.batch_id, AuditEventType.RECORD_VALIDATED, self.actor, result.validated_at or datetime.now(timezone.utc), 1, self.validation_version, batch_id=batch.batch_id, record_id=raw.raw_record_id))
        self._emit(result, raw)
        return result

    def validate_batch(self, batch_id: str) -> list[ValidationResult]:
        batch = self.database.batches.get(batch_id)
        if batch is None:
            raise ValueError("batch does not exist")
        if batch.state is BatchState.RECEIVED:
            event = self._batch_event(batch, BatchState.VALIDATING)
            batch = self.database.batches.transition_with_audit(batch, BatchState.VALIDATING, event)
        results = [self.validate_record(raw.raw_record_id) for raw in self.database.raw_records.list_for_batch(batch_id)]
        batch = self.database.batches.get(batch_id)
        if batch and batch.state is BatchState.VALIDATING:
            self.database.batches.transition_with_audit(batch, BatchState.VALIDATED, self._batch_event(batch, BatchState.VALIDATED))
        return results

    def _errors(self, schema: str, payload: Mapping[str, Any]) -> list[dict[str, str]]:
        if schema not in _SCHEMAS:
            return [{"category": "structural", "field": "schema_version", "code": "unsupported_schema", "message": "unsupported schema version"}]
        fields = _SCHEMAS[schema]
        errors: list[dict[str, str]] = []
        for key in sorted(set(payload) - set(fields)):
            errors.append({"category": "structural", "field": str(key), "code": "unknown_field", "message": "field is not defined by schema"})
        for canonical in sorted(_REQUIRED):
            source_key = next(key for key, value in fields.items() if value == canonical)
            if source_key not in payload:
                errors.append({"category": "structural", "field": source_key, "code": "required", "message": "required field is missing"})
        for source_key, canonical in sorted(fields.items()):
            if source_key not in payload:
                continue
            value = payload[source_key]
            if canonical in {"record_id", "occurred_at", "amount", "currency", "direction", "account_reference", "transaction_reference", "description", "transaction_type"} and not isinstance(value, str):
                errors.append({"category": "structural", "field": source_key, "code": "type", "message": "value must be a string"})
                continue
            if canonical == "record_id" and not value.strip(): errors.append({"category": "business", "field": source_key, "code": "empty", "message": "identifier must not be empty"})
            elif canonical == "occurred_at" and not self._valid_date(value): errors.append({"category": "semantic", "field": source_key, "code": "date", "message": "must be ISO-8601 with offset or YYYY-MM-DD"})
            elif canonical == "amount" and not self._valid_amount(value): errors.append({"category": "semantic", "field": source_key, "code": "amount", "message": "must be decimal with up to 4 fractional digits"})
            elif canonical == "currency" and (len(value) != 3 or not value.isascii() or not value.isalpha() or not value.isupper()): errors.append({"category": "semantic", "field": source_key, "code": "currency", "message": "must be uppercase three-letter code"})
            elif canonical == "direction" and value not in {"CREDIT", "DEBIT"}: errors.append({"category": "business", "field": source_key, "code": "direction", "message": "must be CREDIT or DEBIT"})
        return errors

    @staticmethod
    def _valid_date(value: str) -> bool:
        try:
            parsed = datetime.fromisoformat(value)
            return bool(_DATE.fullmatch(value)) or parsed.utcoffset() is not None
        except (ValueError, TypeError): return False

    @staticmethod
    def _valid_amount(value: str) -> bool:
        if not _AMOUNT.fullmatch(value): return False
        try: return Decimal(value).is_finite()
        except InvalidOperation: return False

    def _batch_event(self, batch: Any, target: BatchState) -> AuditEvent:
        digest = hashlib.sha256(f"BATCH_STATE_CHANGED:{batch.batch_id}:{batch.state.value}:{target.value}:{self.validation_version}".encode()).hexdigest()
        return AuditEvent("audit:" + digest, "batch", batch.batch_id, AuditEventType.BATCH_STATE_CHANGED, self.actor, datetime.now(timezone.utc), 1, self.validation_version, previous_state=batch.state.value, new_state=target.value, batch_id=batch.batch_id)

    def _emit(self, result: ValidationResult, raw: Any) -> None:
        if self.telemetry:
            self.telemetry.emit(TelemetryEvent("ledger.validation.record_invalid" if result.status == "INVALID" else "ledger.validation.record_valid", CorrelationContext(batch_id=raw.batch_id, record_id=raw.raw_record_id), {"source_id": raw.source_id, "schema_version": raw.schema_version, "validation_version": self.validation_version, "validation_id": result.validation_id, "error_count": len(result.errors)}))


Validation = ValidationService
