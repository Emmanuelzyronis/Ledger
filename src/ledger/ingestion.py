"""Layer 4 raw ingestion: immutable envelopes, identity, and replay handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from .domain import AuditEvent, AuditEventType, Batch, BatchCounters, RawRecord, Source
from .identity import canonical_json, raw_fingerprint, raw_identity
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return canonical_json(payload)


def content_fingerprint(payload: Mapping[str, Any]) -> str:
    return raw_fingerprint(payload)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    batch_id: str
    raw_record_id: str | None
    status: str
    fingerprint: str | None = None
    invalid_reason: str | None = None
    duplicate_submission: bool = False


class RawIngestion:
    """Coordinates source registration, batches, and raw record persistence."""

    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None, actor: str = "system") -> None:
        self.database = database
        self.telemetry = telemetry
        self.actor = actor

    def register_source(self, source_id: str, name: str, schema_versions: Sequence[str], *, active: bool = True) -> Source:
        source = Source(source_id, name, tuple(schema_versions), active)
        existing = self.database.sources.get(source_id)
        if existing is not None:
            if existing != source:
                raise ValueError("source is already registered with different metadata")
            return existing
        return self.database.sources.save(source)

    def create_batch(self, source_id: str, external_batch_id: str, schema_version: str, *, batch_id: str | None = None, received_at: datetime | None = None) -> Batch:
        source = self.database.sources.get(source_id)
        if source is None or not source.active:
            raise ValueError("source is unknown or inactive")
        if schema_version not in source.schema_versions:
            raise ValueError("schema version is not registered for source")
        existing = self.database.connection.execute(
            "SELECT batch_id FROM batches WHERE source_id = ? AND external_batch_id = ? AND schema_version = ?",
            (source_id, external_batch_id, schema_version),
        ).fetchone()
        if existing is not None:
            return self.database.batches.get(existing["batch_id"])  # type: ignore[return-value]
        batch = Batch(batch_id or "batch-" + uuid.uuid4().hex, source_id, external_batch_id, schema_version, received_at or datetime.now(timezone.utc))
        self.database.batches.save(batch)
        self._audit(batch, AuditEventType.BATCH_RECEIVED, batch.batch_id)
        return batch

    def ingest(self, batch_id: str, payload: Mapping[str, Any] | Any, *, idempotency_key: str | None = None, accepted_at: datetime | None = None) -> IngestionResult:
        batch = self.database.batches.get(batch_id)
        if batch is None:
            raise ValueError("batch does not exist")
        explicit_key = idempotency_key is not None
        key = idempotency_key or self._fallback_key(batch, payload)
        prior = self.database.raw_records.get_submission(batch.source_id, key)
        if prior is not None:
            result = IngestionResult(**prior, duplicate_submission=True)
            with self.database.transaction():
                if not explicit_key and result.raw_record_id:
                    self.database.raw_records.associate_batch(result.raw_record_id, batch.batch_id)
                if result.raw_record_id:
                    self._audit(batch, AuditEventType.SUBMISSION_DUPLICATE, result.raw_record_id)
            self._emit("ledger.ingestion.submission_duplicate", batch, result.raw_record_id)
            return result

        now = accepted_at or datetime.now(timezone.utc)
        fingerprint: str | None = None
        raw_id: str | None = None
        invalid_reason: str | None = None
        record = None
        if not isinstance(payload, Mapping):
            invalid_reason = "payload must be a JSON object"
        else:
            fingerprint = content_fingerprint(payload)
            raw_id = raw_identity(batch.source_id, batch.schema_version, fingerprint)
            # Identical content already accepted into this same batch is a
            # duplicate submission regardless of the idempotency key. It must
            # not create a second raw record, increment batch counters, or add
            # another audit event.
            linked = self.database.raw_records.find_linked(raw_id, batch.batch_id)
            if linked is not None and canonical_json(linked.payload) == canonical_json(payload):
                return self._duplicate_submission(batch, linked, fingerprint)
            source_key = "record_id" if batch.schema_version == "source_a.v1" else "id"
            source_record_id = payload.get(source_key)
            if not isinstance(source_record_id, str) or not source_record_id.strip():
                invalid_reason = f"missing {source_key}"
                source_record_id = f"invalid-{fingerprint[:16]}"
            previous = self.database.raw_records.find_by_source_record(batch.source_id, batch.schema_version, source_record_id)
            supersedes = previous[-1].raw_record_id if previous and previous[-1].content_fingerprint != fingerprint else None
            record = RawRecord(raw_id, batch.source_id, batch.batch_id, source_record_id, batch.schema_version, payload, fingerprint, now, invalid_reason, supersedes)
        counters = batch.counters
        if invalid_reason and raw_id is None:
            counters = BatchCounters(received_count=counters.received_count + 1, accepted_count=counters.accepted_count, rejected_input_count=counters.rejected_input_count + 1, invalid_count=counters.invalid_count, processed_count=counters.processed_count, matched_count=counters.matched_count, mismatched_count=counters.mismatched_count, unmatched_count=counters.unmatched_count, ambiguous_count=counters.ambiguous_count, duplicate_count=counters.duplicate_count, failed_count=counters.failed_count)
            status = "REJECTED"
        else:
            counters = BatchCounters(received_count=counters.received_count + 1, accepted_count=counters.accepted_count + 1, rejected_input_count=counters.rejected_input_count, invalid_count=counters.invalid_count + bool(invalid_reason), processed_count=counters.processed_count + bool(invalid_reason), matched_count=counters.matched_count, mismatched_count=counters.mismatched_count, unmatched_count=counters.unmatched_count, ambiguous_count=counters.ambiguous_count, duplicate_count=counters.duplicate_count, failed_count=counters.failed_count)
            status = "INVALID" if invalid_reason else "ACCEPTED"
        with self.database.transaction():
            if record is not None:
                raw_id = self.database.raw_records.save(record).raw_record_id
            self.database.batches.update_counters(batch.batch_id, counters)
            result = IngestionResult(batch.batch_id, raw_id, status, fingerprint, invalid_reason)
            self.database.raw_records.save_submission(batch.source_id, key, {"batch_id": result.batch_id, "raw_record_id": result.raw_record_id, "status": result.status, "fingerprint": result.fingerprint, "invalid_reason": result.invalid_reason})
            if raw_id:
                self._audit(batch, AuditEventType.RECORD_INVALID if invalid_reason else AuditEventType.RECORD_INGESTED, raw_id)
        self._emit("ledger.ingestion.record_invalid" if invalid_reason else "ledger.ingestion.record_accepted", batch, raw_id)
        return result

    def _duplicate_submission(self, batch: Batch, existing: RawRecord, fingerprint: str) -> IngestionResult:
        """Record and return an idempotent duplicate of content already in the batch.

        No submission row is written for the new idempotency key: the result is
        derived deterministically from the linked raw record, so any later call
        with that key reaches the same outcome without extra state.
        """
        result = IngestionResult(
            batch.batch_id,
            existing.raw_record_id,
            "INVALID" if existing.invalid_reason else "ACCEPTED",
            fingerprint,
            existing.invalid_reason,
            True,
        )
        with self.database.transaction():
            self._audit(batch, AuditEventType.SUBMISSION_DUPLICATE, existing.raw_record_id)
        self._emit("ledger.ingestion.submission_duplicate", batch, existing.raw_record_id)
        return result

    def ingest_batch(self, batch_id: str, payloads: Sequence[Mapping[str, Any] | Any], *, idempotency_prefix: str | None = None) -> list[IngestionResult]:
        return [self.ingest(batch_id, payload, idempotency_key=(f"{idempotency_prefix}:{index}" if idempotency_prefix else None)) for index, payload in enumerate(payloads)]

    def _fallback_key(self, batch: Batch, payload: Any) -> str:
        if isinstance(payload, Mapping):
            return raw_identity(batch.source_id, batch.schema_version, payload)
        return f"raw:{batch.source_id}:{batch.schema_version}:{hashlib.sha256(repr(payload).encode()).hexdigest()}"

    def _audit(self, batch: Batch, event_type: AuditEventType, record_id: str) -> None:
        digest = hashlib.sha256(f"{event_type.value}:batch:{batch.batch_id}:{record_id}:ingestion_v1".encode()).hexdigest()
        self.database.audit_events.append(AuditEvent(f"audit:{digest}", "batch", batch.batch_id, event_type, self.actor, datetime.now(timezone.utc), 1, "ingestion_v1", batch_id=batch.batch_id, record_id=record_id))

    def _emit(self, name: str, batch: Batch, record_id: str | None) -> None:
        if self.telemetry:
            self.telemetry.emit(TelemetryEvent(name, CorrelationContext(batch_id=batch.batch_id, record_id=record_id), {"source_id": batch.source_id, "schema_version": batch.schema_version}))


IngestionService = RawIngestion
