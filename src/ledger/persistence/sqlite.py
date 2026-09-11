"""SQLite relational authority for the LEDGER domain.

The persistence layer stores domain entities without adding business semantics.
Historical entities are insert-only; mutable operational state is updated only
through domain transition methods and an atomic state-plus-audit operation.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from enum import Enum
from dataclasses import replace
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator
from collections.abc import Mapping

from ..migrations import MigrationRunner

from ledger.domain import (
    AuditEvent,
    AuditEventType,
    Batch,
    BatchCounters,
    BatchState,
    CanonicalTransaction,
    Direction,
    Discrepancy,
    DiscrepancyState,
    MatchCandidate,
    ProcessingAttempt,
    ProcessingAttemptState,
    RawRecord,
    Reconciliation,
    ReconciliationOutcome,
    ReconciliationState,
    Resolution,
    ResolutionType,
    Source,
    ValidationResult,
)
from ledger.domain.errors import InvalidTransitionError, InvalidValueError


class PersistenceError(RuntimeError):
    """Raised when persistence cannot satisfy its contract."""


class UniqueConstraintError(PersistenceError):
    """Raised when a distinct authoritative record uses an occupied identity."""


def _json(value: object) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _canonical_json(value: object) -> str:
    """Serialize payloads using the ingestion identity canonicalization rules."""
    import unicodedata

    def canonical(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(key): canonical(item[key]) for key in sorted(item, key=lambda key: str(key))}
        if isinstance(item, (list, tuple)):
            return [canonical(entry) for entry in item]
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item.replace("\r\n", "\n").replace("\r", "\n"))
        return item

    return json.dumps(canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mapping(value: object) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else {}


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class _SynchronizedConnection:
    """Serialize access to one SQLite connection shared across service threads.

    A service process may serve requests on worker threads while the SQLite
    connection is shared. SQLite requires serialized access on a single
    connection, so every operation acquires one re-entrant lock. The lock is
    re-entrant so a transaction may nest statement execution.
    """

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_lock", lock)

    def execute(self, *args: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.execute(*args)

    def executescript(self, *args: Any) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.executescript(*args)

    def commit(self) -> None:
        with self._lock:
            self._connection.commit()

    def rollback(self) -> None:
        with self._lock:
            self._connection.rollback()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @property
    def in_transaction(self) -> bool:
        with self._lock:
            return self._connection.in_transaction

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_connection"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        with object.__getattribute__(self, "_lock"):
            setattr(object.__getattribute__(self, "_connection"), name, value)


class LedgerDatabase:
    """A strongly consistent relational store and repository registry."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self.connection = _SynchronizedConnection(
            sqlite3.connect(self.path, check_same_thread=False), self._lock)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        # Versioned history on top of the idempotent baseline schema; see
        # ledger.migrations for the ordering and adoption rules.
        self.migrations = MigrationRunner(self)
        self.migrations.apply()
        self.sources = SourceRepository(self)
        self.batches = BatchRepository(self)
        self.processing_attempts = ProcessingAttemptRepository(self)
        self.raw_records = RawRecordRepository(self)
        self.validation_results = ValidationResultRepository(self)
        self.canonical_transactions = CanonicalTransactionRepository(self)
        self.match_candidates = MatchCandidateRepository(self)
        self.reconciliations = ReconciliationRepository(self)
        self.discrepancies = DiscrepancyRepository(self)
        self.resolutions = ResolutionRepository(self)
        self.audit_events = AuditEventRepository(self)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LedgerDatabase":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a group of writes atomically, including state and audit rows."""

        with self._lock:
            if self.connection.in_transaction:
                yield self.connection
                return
            # Serialize writers so per-entity audit sequence allocation is safe.
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except Exception:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def _write(self, operation: Any) -> Any:
        if self.connection.in_transaction:
            return operation()
        with self.transaction():
            return operation()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schema_versions_json TEXT NOT NULL,
                active INTEGER NOT NULL CHECK (active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(source_id),
                external_batch_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                received_at TEXT NOT NULL,
                state TEXT NOT NULL,
                counters_json TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_summary TEXT,
                UNIQUE (source_id, external_batch_id, schema_version)
            );
            CREATE TABLE IF NOT EXISTS processing_attempts (
                attempt_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                processing_version TEXT NOT NULL,
                state TEXT NOT NULL,
                retry_of_attempt_id TEXT REFERENCES processing_attempts(attempt_id),
                started_at TEXT,
                ended_at TEXT,
                error_information TEXT,
                counters_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS raw_records (
                raw_record_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(source_id),
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                source_record_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                invalid_reason TEXT,
                supersedes_raw_record_id TEXT REFERENCES raw_records(raw_record_id),
                UNIQUE (source_id, schema_version, content_fingerprint)
            );
            CREATE TABLE IF NOT EXISTS raw_record_batches (
                raw_record_id TEXT NOT NULL REFERENCES raw_records(raw_record_id),
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                PRIMARY KEY (raw_record_id, batch_id)
            );
            CREATE TABLE IF NOT EXISTS validation_results (
                validation_id TEXT PRIMARY KEY,
                raw_record_id TEXT NOT NULL REFERENCES raw_records(raw_record_id),
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                schema_version TEXT NOT NULL,
                validation_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('VALID','INVALID')),
                errors_json TEXT NOT NULL,
                validated_at TEXT NOT NULL,
                UNIQUE (raw_record_id, validation_version)
            );
            CREATE TRIGGER IF NOT EXISTS validation_results_no_update
            BEFORE UPDATE ON validation_results BEGIN SELECT RAISE(ABORT, 'validation results are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS validation_results_no_delete
            BEFORE DELETE ON validation_results BEGIN SELECT RAISE(ABORT, 'validation results are append-only'); END;
            CREATE TABLE IF NOT EXISTS ingestion_submissions (
                source_id TEXT NOT NULL REFERENCES sources(source_id),
                idempotency_key TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (source_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS canonical_transactions (
                canonical_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(source_id),
                raw_record_id TEXT NOT NULL REFERENCES raw_records(raw_record_id),
                source_record_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                direction TEXT NOT NULL,
                normalization_version TEXT NOT NULL,
                canonical_version INTEGER NOT NULL CHECK (canonical_version > 0),
                transaction_type TEXT,
                account_reference TEXT,
                transaction_reference TEXT,
                description TEXT,
                transaction_status TEXT,
                supersedes_canonical_id TEXT REFERENCES canonical_transactions(canonical_id),
                canonical_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (raw_record_id, normalization_version, canonical_version)
            );
            CREATE TABLE IF NOT EXISTS match_candidates (
                candidate_id TEXT PRIMARY KEY,
                source_a_canonical_id TEXT NOT NULL REFERENCES canonical_transactions(canonical_id),
                source_b_canonical_id TEXT NOT NULL REFERENCES canonical_transactions(canonical_id),
                eligible_rule_ids_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                CHECK (source_a_canonical_id <> source_b_canonical_id),
                UNIQUE (source_a_canonical_id, source_b_canonical_id)
            );
            CREATE TABLE IF NOT EXISTS reconciliations (
                reconciliation_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                source_a_record_id TEXT REFERENCES canonical_transactions(canonical_id),
                source_b_record_id TEXT REFERENCES canonical_transactions(canonical_id),
                raw_record_id TEXT REFERENCES raw_records(raw_record_id),
                reconciliation_version INTEGER NOT NULL CHECK (reconciliation_version > 0),
                rule_version TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                state TEXT NOT NULL,
                outcome TEXT,
                supersedes_reconciliation_id TEXT REFERENCES reconciliations(reconciliation_id),
                resolution_id TEXT,
                UNIQUE (source_a_record_id, source_b_record_id, reconciliation_version),
                CHECK (outcome <> 'INVALID' OR (raw_record_id IS NOT NULL AND source_a_record_id IS NULL AND source_b_record_id IS NULL))
            );
            CREATE TABLE IF NOT EXISTS discrepancies (
                discrepancy_id TEXT PRIMARY KEY,
                reconciliation_id TEXT NOT NULL REFERENCES reconciliations(reconciliation_id),
                reason TEXT NOT NULL,
                state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS resolutions (
                resolution_id TEXT PRIMARY KEY,
                discrepancy_id TEXT NOT NULL REFERENCES discrepancies(discrepancy_id),
                reconciliation_id TEXT NOT NULL REFERENCES reconciliations(reconciliation_id),
                resolution_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                rule_version TEXT
                ,UNIQUE (discrepancy_id)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                stage_version TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                previous_state TEXT,
                new_state TEXT,
                batch_id TEXT REFERENCES batches(batch_id),
                attempt_id TEXT REFERENCES processing_attempts(attempt_id),
                record_id TEXT,
                reconciliation_id TEXT REFERENCES reconciliations(reconciliation_id),
                causation_event_id TEXT,
                UNIQUE (entity_type, entity_id, sequence)
            );
            CREATE TRIGGER IF NOT EXISTS raw_records_no_update
            BEFORE UPDATE ON raw_records BEGIN SELECT RAISE(ABORT, 'raw records are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS raw_records_no_delete
            BEFORE DELETE ON raw_records BEGIN SELECT RAISE(ABORT, 'raw records are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS canonical_transactions_no_update
            BEFORE UPDATE ON canonical_transactions BEGIN SELECT RAISE(ABORT, 'canonical transactions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS canonical_transactions_no_delete
            BEFORE DELETE ON canonical_transactions BEGIN SELECT RAISE(ABORT, 'canonical transactions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS match_candidates_no_update
            BEFORE UPDATE ON match_candidates BEGIN SELECT RAISE(ABORT, 'match candidates are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS match_candidates_no_delete
            BEFORE DELETE ON match_candidates BEGIN SELECT RAISE(ABORT, 'match candidates are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS reconciliations_no_update
            BEFORE UPDATE ON reconciliations BEGIN SELECT RAISE(ABORT, 'reconciliations are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS reconciliations_no_delete
            BEFORE DELETE ON reconciliations BEGIN SELECT RAISE(ABORT, 'reconciliations are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS resolutions_no_update
            BEFORE UPDATE ON resolutions BEGIN SELECT RAISE(ABORT, 'resolutions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS resolutions_no_delete
            BEFORE DELETE ON resolutions BEGIN SELECT RAISE(ABORT, 'resolutions are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
            CREATE INDEX IF NOT EXISTS idx_reconciliations_supersedes
            ON reconciliations(supersedes_reconciliation_id);
            CREATE INDEX IF NOT EXISTS idx_reconciliations_source_b
            ON reconciliations(source_b_record_id);
            """
        )
        self.connection.commit()


class _Repository:
    def __init__(self, database: LedgerDatabase) -> None:
        self.database = database

    @property
    def connection(self) -> sqlite3.Connection:
        return self.database.connection

    def _insert(self, sql: str, values: tuple[Any, ...]) -> None:
        try:
            self.connection.execute(sql, values)
        except sqlite3.IntegrityError as exc:
            raise UniqueConstraintError(str(exc)) from exc


class SourceRepository(_Repository):
    def save(self, source: Source) -> Source:
        def operation() -> Source:
            self._insert(
                "INSERT INTO sources(source_id,name,schema_versions_json,active) VALUES (?,?,?,?)",
                (source.source_id, source.name, _json(source.schema_versions), int(source.active)),
            )
            return source

        return self.database._write(operation)

    def get(self, source_id: str) -> Source | None:
        row = self.connection.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
        return None if row is None else Source(row["source_id"], row["name"], tuple(_mapping(row["schema_versions_json"])), bool(row["active"]))


class BatchRepository(_Repository):
    def save(self, batch: Batch) -> Batch:
        def operation() -> Batch:
            self._insert(
                "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    batch.batch_id, batch.source_id, batch.external_batch_id, batch.schema_version,
                    _timestamp(batch.received_at), batch.state.value, _json(batch.counters.__dict__ if hasattr(batch.counters, "__dict__") else {
                        field: getattr(batch.counters, field) for field in BatchCounters.__dataclass_fields__
                    }), _timestamp(batch.started_at), _timestamp(batch.completed_at), batch.error_summary,
                ),
            )
            return batch

        return self.database._write(operation)

    def get(self, batch_id: str) -> Batch | None:
        row = self.connection.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is None:
            return None
        return Batch(
            row["batch_id"], row["source_id"], row["external_batch_id"], row["schema_version"],
            _parse_timestamp(row["received_at"]), BatchState(row["state"]),
            BatchCounters(**_mapping(row["counters_json"])), _parse_timestamp(row["started_at"]),
            _parse_timestamp(row["completed_at"]), row["error_summary"],
        )

    def update_counters(self, batch_id: str, counters: BatchCounters) -> Batch:
        def operation() -> Batch:
            updated = self.connection.execute(
                "UPDATE batches SET counters_json = ? WHERE batch_id = ?",
                (_json({field: getattr(counters, field) for field in BatchCounters.__dataclass_fields__}), batch_id),
            )
            if updated.rowcount != 1:
                raise PersistenceError("batch does not exist")
            return self.get(batch_id)  # type: ignore[return-value]
        return self.database._write(operation)

    def transition_with_audit(
        self,
        batch: Batch,
        target: BatchState,
        event: AuditEvent,
        *,
        retry: bool = False,
        attempt_created: bool = False,
    ) -> Batch:
        next_batch = batch.transition_to(target, retry=retry, attempt_created=attempt_created)

        def operation() -> Batch:
            updated = self.connection.execute(
                "UPDATE batches SET state = ?, started_at = ?, completed_at = ?, error_summary = ? WHERE batch_id = ? AND state = ?",
                (next_batch.state.value, _timestamp(next_batch.started_at), _timestamp(next_batch.completed_at), next_batch.error_summary, batch.batch_id, batch.state.value),
            )
            if updated.rowcount != 1:
                raise InvalidTransitionError("batch state changed concurrently or does not exist")
            self.database.audit_events.append(event)
            return next_batch

        return self.database._write(operation)


class ProcessingAttemptRepository(_Repository):
    def save(self, attempt: ProcessingAttempt) -> ProcessingAttempt:
        def operation() -> ProcessingAttempt:
            self._insert(
                "INSERT INTO processing_attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (attempt.attempt_id, attempt.batch_id, attempt.processing_version, attempt.state.value, attempt.retry_of_attempt_id,
                 _timestamp(attempt.started_at), _timestamp(attempt.ended_at), attempt.error_information,
                 _json({field: getattr(attempt.counters, field) for field in BatchCounters.__dataclass_fields__})),
            )
            return attempt

        return self.database._write(operation)

    def get(self, attempt_id: str) -> ProcessingAttempt | None:
        row = self.connection.execute("SELECT * FROM processing_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if row is None:
            return None
        return ProcessingAttempt(row["attempt_id"], row["batch_id"], row["processing_version"], ProcessingAttemptState(row["state"]),
                                 row["retry_of_attempt_id"], _parse_timestamp(row["started_at"]), _parse_timestamp(row["ended_at"]),
                                 row["error_information"], BatchCounters(**_mapping(row["counters_json"])))

    def transition_with_audit(
        self,
        attempt: ProcessingAttempt,
        target: ProcessingAttemptState,
        event: AuditEvent,
        *,
        at: datetime | None = None,
        error: str | None = None,
    ) -> ProcessingAttempt:
        next_attempt = attempt.transition_to(target, at=at, error=error)

        def operation() -> ProcessingAttempt:
            updated = self.connection.execute(
                "UPDATE processing_attempts SET state = ?, started_at = ?, ended_at = ?, error_information = ? WHERE attempt_id = ? AND state = ?",
                (next_attempt.state.value, _timestamp(next_attempt.started_at), _timestamp(next_attempt.ended_at), next_attempt.error_information,
                 attempt.attempt_id, attempt.state.value),
            )
            if updated.rowcount != 1:
                raise InvalidTransitionError("processing attempt state changed concurrently or does not exist")
            self.database.audit_events.append(event)
            return next_attempt

        return self.database._write(operation)


class RawRecordRepository(_Repository):
    def associate_batch(self, raw_record_id: str, batch_id: str) -> None:
        self.database._write(lambda: self.connection.execute(
            "INSERT OR IGNORE INTO raw_record_batches(raw_record_id,batch_id) VALUES (?,?)",
            (raw_record_id, batch_id),
        ))

    def find_linked(self, raw_record_id: str, batch_id: str) -> RawRecord | None:
        """Return the raw record only if it is already associated with the batch.

        Used by ingestion to detect a resubmission whose content was already
        accepted into this batch under a different idempotency key.
        """
        row = self.connection.execute(
            "SELECT raw_record_id FROM raw_record_batches WHERE raw_record_id = ? AND batch_id = ?",
            (raw_record_id, batch_id),
        ).fetchone()
        return None if row is None else self.get(raw_record_id)

    def save(self, record: RawRecord) -> RawRecord:
        def operation() -> RawRecord:
            existing = self.connection.execute(
                "SELECT * FROM raw_records WHERE source_id = ? AND schema_version = ? AND content_fingerprint = ?",
                (record.source_id, record.schema_version, record.content_fingerprint),
            ).fetchone()
            if existing is not None:
                if _canonical_json(json.loads(existing["payload_json"])) != _canonical_json(record.payload):
                    raise PersistenceError("content fingerprint collision detected")
                self.connection.execute("INSERT OR IGNORE INTO raw_record_batches VALUES (?,?)", (existing["raw_record_id"], record.batch_id))
                return self.get(existing["raw_record_id"])  # type: ignore[return-value]
            self._insert(
                "INSERT INTO raw_records VALUES (?,?,?,?,?,?,?,?,?,?)",
                (record.raw_record_id, record.source_id, record.batch_id, record.source_record_id, record.schema_version,
                 _json(record.payload), record.content_fingerprint, _timestamp(record.accepted_at), record.invalid_reason, record.supersedes_raw_record_id),
            )
            self.connection.execute("INSERT INTO raw_record_batches VALUES (?,?)", (record.raw_record_id, record.batch_id))
            return record

        return self.database._write(operation)

    def get(self, raw_record_id: str) -> RawRecord | None:
        row = self.connection.execute("SELECT * FROM raw_records WHERE raw_record_id = ?", (raw_record_id,)).fetchone()
        if row is None:
            return None
        return RawRecord(row["raw_record_id"], row["source_id"], row["batch_id"], row["source_record_id"], row["schema_version"],
                         _mapping(row["payload_json"]), row["content_fingerprint"], _parse_timestamp(row["accepted_at"]), row["invalid_reason"], row["supersedes_raw_record_id"])

    def find_by_source_record(self, source_id: str, schema_version: str, source_record_id: str) -> list[RawRecord]:
        rows = self.connection.execute(
            "SELECT raw_record_id FROM raw_records WHERE source_id = ? AND schema_version = ? AND source_record_id = ? ORDER BY accepted_at, raw_record_id",
            (source_id, schema_version, source_record_id),
        ).fetchall()
        return [self.get(row["raw_record_id"]) for row in rows]  # type: ignore[misc]

    def list_for_batch(self, batch_id: str) -> list[RawRecord]:
        rows = self.connection.execute("SELECT raw_record_id FROM raw_record_batches WHERE batch_id = ? ORDER BY raw_record_id", (batch_id,)).fetchall()
        return [self.get(row["raw_record_id"]) for row in rows]  # type: ignore[misc]

    def save_submission(self, source_id: str, idempotency_key: str, result: Mapping[str, Any]) -> bool:
        try:
            self.connection.execute(
                "INSERT INTO ingestion_submissions(source_id,idempotency_key,result_json) VALUES (?,?,?)",
                (source_id, idempotency_key, _json(result)),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_submission(self, source_id: str, idempotency_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT result_json FROM ingestion_submissions WHERE source_id = ? AND idempotency_key = ?",
            (source_id, idempotency_key),
        ).fetchone()
        return None if row is None else _mapping(row["result_json"])


class ValidationResultRepository(_Repository):
    def save(self, result: ValidationResult) -> ValidationResult:
        def operation() -> ValidationResult:
            existing = self.connection.execute("SELECT * FROM validation_results WHERE raw_record_id = ? AND validation_version = ?", (result.raw_record_id, result.validation_version)).fetchone()
            if existing is not None:
                return self.get(existing["validation_id"])  # type: ignore[return-value]
            self._insert("INSERT INTO validation_results VALUES (?,?,?,?,?,?,?,?)", (result.validation_id, result.raw_record_id, result.batch_id, result.schema_version, result.validation_version, result.status, _json(result.errors), _timestamp(result.validated_at)))
            return result
        return self.database._write(operation)

    def get(self, validation_id: str) -> ValidationResult | None:
        row = self.connection.execute("SELECT * FROM validation_results WHERE validation_id = ?", (validation_id,)).fetchone()
        if row is None:
            return None
        errors = tuple(dict(item) for item in json.loads(row["errors_json"]))
        return ValidationResult(row["validation_id"], row["raw_record_id"], row["batch_id"], row["schema_version"], row["validation_version"], row["status"], errors, _parse_timestamp(row["validated_at"]))

    def get_for_raw(self, raw_record_id: str, validation_version: str) -> ValidationResult | None:
        row = self.connection.execute("SELECT validation_id FROM validation_results WHERE raw_record_id = ? AND validation_version = ?", (raw_record_id, validation_version)).fetchone()
        return None if row is None else self.get(row["validation_id"])


class CanonicalTransactionRepository(_Repository):
    def save(self, transaction: CanonicalTransaction) -> CanonicalTransaction:
        def operation() -> CanonicalTransaction:
            existing = self.connection.execute(
                "SELECT canonical_id FROM canonical_transactions WHERE canonical_id = ? OR (raw_record_id = ? AND normalization_version = ? AND canonical_version = ?)",
                (transaction.canonical_id, transaction.raw_record_id, transaction.normalization_version, transaction.canonical_version),
            ).fetchone()
            if existing is not None:
                persisted = self.get(existing["canonical_id"])
                if persisted is None:
                    raise PersistenceError("canonical identity lookup failed")
                if persisted.canonical_id != transaction.canonical_id or persisted.canonical_fingerprint != transaction.canonical_fingerprint or persisted.semantic_payload() != transaction.semantic_payload():
                    raise UniqueConstraintError("canonical identity collision")
                return persisted
            self._insert(
                "INSERT INTO canonical_transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (transaction.canonical_id, transaction.source_id, transaction.raw_record_id, transaction.source_record_id,
                 _timestamp(transaction.occurred_at), format(transaction.amount, "f"), transaction.currency, transaction.direction.value,
                 transaction.normalization_version, transaction.canonical_version, transaction.transaction_type, transaction.account_reference,
                 transaction.transaction_reference, transaction.description, transaction.transaction_status, transaction.supersedes_canonical_id,
                 transaction.canonical_fingerprint, _timestamp(transaction.created_at)),
            )
            return transaction

        return self.database._write(operation)

    def get(self, canonical_id: str) -> CanonicalTransaction | None:
        row = self.connection.execute("SELECT * FROM canonical_transactions WHERE canonical_id = ?", (canonical_id,)).fetchone()
        if row is None:
            return None
        return CanonicalTransaction(row["canonical_id"], row["source_id"], row["raw_record_id"], row["source_record_id"],
                                    _parse_timestamp(row["occurred_at"]), Decimal(row["amount"]), row["currency"], Direction(row["direction"]),
                                    row["normalization_version"], row["canonical_version"], row["canonical_fingerprint"], _parse_timestamp(row["created_at"]),
                                    row["transaction_type"], row["account_reference"], row["transaction_reference"], row["description"],
                                    row["transaction_status"], row["supersedes_canonical_id"])

    def get_for_raw_version(self, raw_record_id: str, normalization_version: str) -> CanonicalTransaction | None:
        row = self.connection.execute(
            "SELECT canonical_id FROM canonical_transactions WHERE raw_record_id = ? AND normalization_version = ? ORDER BY canonical_version LIMIT 1",
            (raw_record_id, normalization_version),
        ).fetchone()
        return None if row is None else self.get(row["canonical_id"])

    def list_for_raw(self, raw_record_id: str) -> list[CanonicalTransaction]:
        rows = self.connection.execute(
            "SELECT canonical_id FROM canonical_transactions WHERE raw_record_id = ? ORDER BY canonical_version",
            (raw_record_id,),
        ).fetchall()
        return [self.get(row["canonical_id"]) for row in rows]  # type: ignore[misc]

    def list_all(self) -> list[CanonicalTransaction]:
        rows = self.connection.execute("SELECT canonical_id FROM canonical_transactions ORDER BY canonical_id").fetchall()
        return [self.get(row["canonical_id"]) for row in rows]  # type: ignore[misc]


class MatchCandidateRepository(_Repository):
    def save(self, candidate: MatchCandidate) -> MatchCandidate:
        def operation() -> MatchCandidate:
            existing = self.connection.execute(
                "SELECT candidate_id FROM match_candidates WHERE candidate_id = ? OR (source_a_canonical_id = ? AND source_b_canonical_id = ?)",
                (candidate.candidate_id, candidate.source_a_canonical_id, candidate.source_b_canonical_id),
            ).fetchone()
            if existing is not None:
                persisted = self.get(existing["candidate_id"])
                if persisted is None:
                    raise PersistenceError("candidate lookup failed")
                if persisted != candidate:
                    raise UniqueConstraintError("candidate identity collision")
                return persisted
            self._insert("INSERT INTO match_candidates VALUES (?,?,?,?,?)", (candidate.candidate_id, candidate.source_a_canonical_id,
                      candidate.source_b_canonical_id, _json(candidate.eligible_rule_ids), _json(candidate.evidence)))
            return candidate

        return self.database._write(operation)

    def get(self, candidate_id: str) -> MatchCandidate | None:
        row = self.connection.execute("SELECT * FROM match_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return None if row is None else MatchCandidate(row["candidate_id"], row["source_a_canonical_id"], row["source_b_canonical_id"],
                                                         tuple(json.loads(row["eligible_rule_ids_json"])), _mapping(row["evidence_json"]))

    def get_for_pair(self, source_a_canonical_id: str, source_b_canonical_id: str) -> MatchCandidate | None:
        row = self.connection.execute("SELECT candidate_id FROM match_candidates WHERE source_a_canonical_id = ? AND source_b_canonical_id = ?", (source_a_canonical_id, source_b_canonical_id)).fetchone()
        return None if row is None else self.get(row["candidate_id"])

    def list_all(self) -> list[MatchCandidate]:
        rows = self.connection.execute("SELECT candidate_id FROM match_candidates ORDER BY candidate_id").fetchall()
        return [self.get(row["candidate_id"]) for row in rows]  # type: ignore[misc]


class ReconciliationRepository(_Repository):
    def save(self, reconciliation: Reconciliation) -> Reconciliation:
        def operation() -> Reconciliation:
            existing = self.connection.execute("SELECT reconciliation_id FROM reconciliations WHERE reconciliation_id = ?", (reconciliation.reconciliation_id,)).fetchone()
            if existing is not None:
                persisted = self.get(existing["reconciliation_id"])
                if persisted != reconciliation:
                    raise UniqueConstraintError("reconciliation identity collision")
                return persisted  # type: ignore[return-value]
            self._insert("INSERT INTO reconciliations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (reconciliation.reconciliation_id,
                      reconciliation.batch_id, reconciliation.source_a_record_id, reconciliation.source_b_record_id,
                      reconciliation.raw_record_id,
                      reconciliation.reconciliation_version, reconciliation.rule_version, _json(reconciliation.evidence), reconciliation.state.value,
                      reconciliation.outcome.value if reconciliation.outcome else None, reconciliation.supersedes_reconciliation_id,
                      reconciliation.resolution_id))
            return reconciliation

        return self.database._write(operation)

    def get(self, reconciliation_id: str) -> Reconciliation | None:
        row = self.connection.execute("SELECT * FROM reconciliations WHERE reconciliation_id = ?", (reconciliation_id,)).fetchone()
        if row is None:
            return None
        return Reconciliation(row["reconciliation_id"], row["batch_id"], row["source_a_record_id"], row["source_b_record_id"],
                              row["reconciliation_version"], row["rule_version"], _mapping(row["evidence_json"]), ReconciliationState(row["state"]),
                              ReconciliationOutcome(row["outcome"]) if row["outcome"] else None, row["supersedes_reconciliation_id"], row["resolution_id"], row["raw_record_id"])

    def list_current(self) -> list[Reconciliation]:
        """Return every reconciliation version that no other version supersedes.

        ``current_state`` for a scope is defined by these rows: a version is
        current unless another immutable version links to it through
        ``supersedes_reconciliation_id``. Superseded versions stay retrievable.
        """
        rows = self.connection.execute(
            "SELECT reconciliation_id FROM reconciliations "
            "WHERE reconciliation_id NOT IN "
            "(SELECT supersedes_reconciliation_id FROM reconciliations "
            " WHERE supersedes_reconciliation_id IS NOT NULL) "
            "ORDER BY reconciliation_id"
        ).fetchall()
        return [self.get(row["reconciliation_id"]) for row in rows]  # type: ignore[misc]

    def find_current_for_participants(self, canonical_ids: set[str]) -> list[Reconciliation]:
        """Return current versions that reference any of the given canonical IDs.

        Indexed lookup: an in-scope late arrival must not force a scan of every
        historical reconciliation version.
        """
        if not canonical_ids:
            return []
        ordered = sorted(canonical_ids)
        placeholders = ",".join("?" for _ in ordered)
        rows = self.connection.execute(
            f"SELECT reconciliation_id FROM reconciliations "
            f"WHERE (source_a_record_id IN ({placeholders}) OR source_b_record_id IN ({placeholders})) "
            f"AND NOT EXISTS (SELECT 1 FROM reconciliations AS superseder "
            f" WHERE superseder.supersedes_reconciliation_id = reconciliations.reconciliation_id) "
            f"ORDER BY reconciliation_id",
            tuple(ordered) * 2,
        ).fetchall()
        return [self.get(row["reconciliation_id"]) for row in rows]  # type: ignore[misc]

    def transition_with_audit(
        self,
        reconciliation: Reconciliation,
        target: ReconciliationState,
        next_reconciliation: Reconciliation,
        event: AuditEvent,
    ) -> Reconciliation:
        """Insert an immutable superseding version and its audit event atomically.

        The caller supplies the new identity/version because identity generation
        belongs to a later application layer. The domain transition is still
        revalidated here before either row is written.
        """
        expected = reconciliation.transition_to(
            target,
            outcome=next_reconciliation.outcome,
            resolution_id=next_reconciliation.resolution_id,
        )
        if (
            next_reconciliation.reconciliation_version != reconciliation.reconciliation_version + 1
            or next_reconciliation.supersedes_reconciliation_id != reconciliation.reconciliation_id
            or next_reconciliation.state != expected.state
            or next_reconciliation.outcome != expected.outcome
        ):
            raise InvalidTransitionError("next reconciliation is not a valid superseding version")

        def operation() -> Reconciliation:
            self.save(next_reconciliation)
            self.database.audit_events.append(event)
            return next_reconciliation

        return self.database._write(operation)


class DiscrepancyRepository(_Repository):
    def save(self, discrepancy: Discrepancy) -> Discrepancy:
        def operation() -> Discrepancy:
            self._insert("INSERT INTO discrepancies VALUES (?,?,?,?)", (discrepancy.discrepancy_id, discrepancy.reconciliation_id, discrepancy.reason, discrepancy.state.value))
            return discrepancy

        return self.database._write(operation)

    def get(self, discrepancy_id: str) -> Discrepancy | None:
        row = self.connection.execute("SELECT * FROM discrepancies WHERE discrepancy_id = ?", (discrepancy_id,)).fetchone()
        return None if row is None else Discrepancy(row["discrepancy_id"], row["reconciliation_id"], row["reason"], DiscrepancyState(row["state"]))

    def transition_with_audit(self, discrepancy: Discrepancy, target: DiscrepancyState, event: AuditEvent) -> Discrepancy:
        next_discrepancy = discrepancy.transition_to(target)

        def operation() -> Discrepancy:
            updated = self.connection.execute("UPDATE discrepancies SET state = ? WHERE discrepancy_id = ? AND state = ?", (target.value, discrepancy.discrepancy_id, discrepancy.state.value))
            if updated.rowcount != 1:
                raise InvalidTransitionError("discrepancy state changed concurrently or does not exist")
            self.database.audit_events.append(event)
            return next_discrepancy

        return self.database._write(operation)


class ResolutionRepository(_Repository):
    def save(self, resolution: Resolution) -> Resolution:
        def operation() -> Resolution:
            existing = self.connection.execute("SELECT resolution_id FROM resolutions WHERE resolution_id = ? OR discrepancy_id = ?", (resolution.resolution_id, resolution.discrepancy_id)).fetchone()
            if existing is not None:
                persisted = self.get(existing["resolution_id"])
                if persisted == resolution:
                    return persisted  # type: ignore[return-value]
                raise UniqueConstraintError("discrepancy already has a different resolution")
            self._insert("INSERT INTO resolutions VALUES (?,?,?,?,?,?,?,?,?)", (resolution.resolution_id, resolution.discrepancy_id,
                      resolution.reconciliation_id, resolution.resolution_type.value, resolution.actor, resolution.reason, _timestamp(resolution.created_at),
                      _json(resolution.evidence), resolution.rule_version))
            return resolution

        return self.database._write(operation)

    def get(self, resolution_id: str) -> Resolution | None:
        row = self.connection.execute("SELECT * FROM resolutions WHERE resolution_id = ?", (resolution_id,)).fetchone()
        if row is None:
            return None
        return Resolution(row["resolution_id"], row["discrepancy_id"], row["reconciliation_id"], ResolutionType(row["resolution_type"]),
                          row["actor"], row["reason"], _parse_timestamp(row["created_at"]), _mapping(row["evidence_json"]), row["rule_version"])

    def apply_with_audit(
        self,
        resolution: Resolution,
        discrepancy: Discrepancy,
        discrepancy_target: DiscrepancyState,
        reconciliation: Reconciliation,
        next_reconciliation: Reconciliation,
        discrepancy_event: AuditEvent,
        reconciliation_event: AuditEvent,
        resolution_event: AuditEvent,
    ) -> tuple[Resolution, Discrepancy, Reconciliation]:
        """Atomically persist a resolution, discrepancy transition, and new reconciliation version."""
        next_discrepancy = discrepancy.transition_to(discrepancy_target)
        expected_reconciliation = reconciliation.transition_to(
            ReconciliationState.RESOLVED,
            resolution_id=resolution.resolution_id,
        )
        if resolution.discrepancy_id != discrepancy.discrepancy_id or resolution.reconciliation_id != reconciliation.reconciliation_id:
            raise InvalidValueError("resolution references do not match the supplied discrepancy and reconciliation")
        if (
            next_reconciliation.reconciliation_version != reconciliation.reconciliation_version + 1
            or next_reconciliation.supersedes_reconciliation_id != reconciliation.reconciliation_id
            or next_reconciliation.state != expected_reconciliation.state
            or next_reconciliation.outcome != expected_reconciliation.outcome
            or next_reconciliation.resolution_id != resolution.resolution_id
        ):
            raise InvalidTransitionError("next reconciliation is not a valid resolved version")

        def operation() -> tuple[Resolution, Discrepancy, Reconciliation]:
            self.database.discrepancies.transition_with_audit(discrepancy, discrepancy_target, discrepancy_event)
            self.database.reconciliations.transition_with_audit(
                reconciliation, ReconciliationState.RESOLVED, next_reconciliation, reconciliation_event
            )
            self.save(resolution)
            self.database.audit_events.append(resolution_event)
            return resolution, next_discrepancy, next_reconciliation

        return self.database._write(operation)

    def apply_terminal_with_audit(
        self,
        resolution: Resolution,
        discrepancy: Discrepancy,
        discrepancy_target: DiscrepancyState,
        discrepancy_event: AuditEvent,
        resolution_event: AuditEvent,
    ) -> tuple[Resolution, Discrepancy]:
        """Atomically persist a deferred/rejected resolution without reopening reconciliation."""
        next_discrepancy = discrepancy.transition_to(discrepancy_target)
        if resolution.discrepancy_id != discrepancy.discrepancy_id or resolution.reconciliation_id is None:
            raise InvalidValueError("resolution references do not match the supplied discrepancy")

        def operation() -> tuple[Resolution, Discrepancy]:
            updated = self.connection.execute(
                "UPDATE discrepancies SET state = ? WHERE discrepancy_id = ? AND state = ?",
                (discrepancy_target.value, discrepancy.discrepancy_id, discrepancy.state.value),
            )
            if updated.rowcount != 1:
                raise InvalidTransitionError("discrepancy state changed concurrently or does not exist")
            self.save(resolution)
            self.database.audit_events.append(discrepancy_event)
            self.database.audit_events.append(resolution_event)
            return resolution, next_discrepancy

        return self.database._write(operation)


class AuditEventRepository(_Repository):
    def append(self, event: AuditEvent) -> AuditEvent:
        def operation() -> AuditEvent:
            existing = self.connection.execute("SELECT * FROM audit_events WHERE event_id = ?", (event.event_id,)).fetchone()
            if existing is not None:
                # `sequence` is assigned by this store on insert, so the caller's
                # value is advisory and must not participate in event identity:
                # comparing it makes replaying an already-appended event fail as
                # a false collision whenever it was not the entity's first event.
                same_event = (
                    existing["entity_type"] == event.entity_type
                    and existing["entity_id"] == event.entity_id
                    and existing["event_type"] == event.event_type.value
                    and existing["stage_version"] == event.stage_version
                    and existing["metadata_json"] == _json(event.metadata)
                    and existing["previous_state"] == event.previous_state
                    and existing["new_state"] == event.new_state
                    and existing["batch_id"] == event.batch_id
                    and existing["attempt_id"] == event.attempt_id
                    and existing["record_id"] == event.record_id
                    and existing["reconciliation_id"] == event.reconciliation_id
                    and existing["causation_event_id"] == event.causation_event_id
                )
                if not same_event:
                    raise UniqueConstraintError("event_id is already used by another logical event")
                return self.get(event.event_id)  # type: ignore[return-value]
            next_sequence = self.connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM audit_events WHERE entity_type = ? AND entity_id = ?",
                (event.entity_type, event.entity_id),
            ).fetchone()[0]
            persisted_event = replace(event, sequence=next_sequence)
            self._insert("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (persisted_event.event_id, persisted_event.entity_type, persisted_event.entity_id,
                      persisted_event.event_type.value, persisted_event.actor, _timestamp(persisted_event.timestamp), persisted_event.sequence, persisted_event.stage_version, _json(persisted_event.metadata),
                      persisted_event.previous_state, persisted_event.new_state, persisted_event.batch_id, persisted_event.attempt_id, persisted_event.record_id, persisted_event.reconciliation_id, persisted_event.causation_event_id))
            return persisted_event

        return self.database._write(operation)

    def get(self, event_id: str) -> AuditEvent | None:
        row = self.connection.execute("SELECT * FROM audit_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        return AuditEvent(row["event_id"], row["entity_type"], row["entity_id"], AuditEventType(row["event_type"]), row["actor"],
                          _parse_timestamp(row["timestamp"]), row["sequence"], row["stage_version"], _mapping(row["metadata_json"]),
                          row["previous_state"], row["new_state"], row["batch_id"], row["attempt_id"], row["record_id"], row["reconciliation_id"], row["causation_event_id"])

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        rows = self.connection.execute("SELECT event_id FROM audit_events WHERE entity_type = ? AND entity_id = ? ORDER BY sequence", (entity_type, entity_id)).fetchall()
        return [self.get(row["event_id"]) for row in rows]  # type: ignore[misc]
