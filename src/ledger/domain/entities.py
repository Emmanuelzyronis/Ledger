"""Immutable domain entities and state transitions for LEDGER Layer 2."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from collections.abc import Mapping

from .errors import InvalidTransitionError, InvalidValueError
from .types import (
    AuditEventType,
    BatchState,
    Direction,
    DiscrepancyState,
    ProcessingAttemptState,
    ReconciliationOutcome,
    ReconciliationState,
    ResolutionType,
    freeze_mapping,
    normalize_text,
    require_amount,
    require_currency,
    require_fingerprint,
    require_id,
    require_utc,
)


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    name: str
    schema_versions: tuple[str, ...]
    active: bool = True

    def __post_init__(self) -> None:
        require_id(self.source_id, "source_id")
        name = normalize_text(self.name, "name")
        if not name:
            raise InvalidValueError("name must not be empty")
        schema_versions = tuple(sorted(normalize_text(version, "schema_version") for version in self.schema_versions))
        if not schema_versions or any(not version for version in schema_versions):
            raise InvalidValueError("at least one schema version is required")
        if len(set(schema_versions)) != len(schema_versions):
            raise InvalidValueError("schema_versions must be unique")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "schema_versions", schema_versions)


@dataclass(frozen=True, slots=True)
class BatchCounters:
    received_count: int = 0
    accepted_count: int = 0
    rejected_input_count: int = 0
    invalid_count: int = 0
    processed_count: int = 0
    matched_count: int = 0
    mismatched_count: int = 0
    unmatched_count: int = 0
    ambiguous_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0

    def __post_init__(self) -> None:
        values = (
            self.received_count,
            self.accepted_count,
            self.rejected_input_count,
            self.invalid_count,
            self.processed_count,
            self.matched_count,
            self.mismatched_count,
            self.unmatched_count,
            self.ambiguous_count,
            self.duplicate_count,
            self.failed_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise InvalidValueError("batch counters must be non-negative integers")
        if self.received_count != self.accepted_count + self.rejected_input_count:
            raise InvalidValueError("received_count must equal accepted_count + rejected_input_count")
        outcome_count = (
            self.matched_count
            + self.mismatched_count
            + self.unmatched_count
            + self.ambiguous_count
            + self.duplicate_count
            + self.invalid_count
        )
        if self.processed_count != outcome_count:
            raise InvalidValueError("processed_count must equal the sum of outcome counters")
        if self.processed_count + self.failed_count > self.accepted_count:
            raise InvalidValueError("processed and failed counts cannot exceed accepted_count")


@dataclass(frozen=True, slots=True)
class Batch:
    batch_id: str
    source_id: str
    external_batch_id: str
    schema_version: str
    received_at: datetime
    state: BatchState = BatchState.RECEIVED
    counters: BatchCounters = field(default_factory=BatchCounters)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        require_id(self.batch_id, "batch_id")
        require_id(self.source_id, "source_id")
        require_id(self.external_batch_id, "external_batch_id")
        require_id(self.schema_version, "schema_version")
        if not isinstance(self.state, BatchState):
            raise InvalidValueError("state must be a BatchState")
        object.__setattr__(self, "received_at", require_utc(self.received_at, "received_at"))
        if self.started_at is not None:
            object.__setattr__(self, "started_at", require_utc(self.started_at, "started_at"))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", require_utc(self.completed_at, "completed_at"))
        object.__setattr__(self, "error_summary", normalize_text(self.error_summary, "error_summary", allow_empty=True))

    def transition_to(self, target: BatchState, *, retry: bool = False, attempt_created: bool = False) -> "Batch":
        if not isinstance(target, BatchState):
            raise InvalidValueError("target must be a BatchState")
        allowed = {
            BatchState.RECEIVED: {BatchState.VALIDATING},
            BatchState.VALIDATING: {BatchState.REJECTED, BatchState.VALIDATED},
            BatchState.VALIDATED: {BatchState.PROCESSING},
            BatchState.PROCESSING: {BatchState.COMPLETED, BatchState.PARTIAL, BatchState.FAILED},
            BatchState.FAILED: {BatchState.PROCESSING},
            BatchState.PARTIAL: {BatchState.PROCESSING},
            BatchState.COMPLETED: set(),
            BatchState.REJECTED: set(),
        }
        if target not in allowed[self.state] or (self.state in {BatchState.FAILED, BatchState.PARTIAL} and not retry):
            raise InvalidTransitionError(f"illegal batch transition {self.state.value} -> {target.value}")
        if target is BatchState.PROCESSING and not attempt_created:
            raise InvalidTransitionError("entering processing requires an explicit processing-attempt context")
        if target is BatchState.COMPLETED and self.counters.failed_count:
            raise InvalidTransitionError("a batch with failed records cannot be completed")
        if target is BatchState.PARTIAL and not self.counters.failed_count:
            raise InvalidTransitionError("a partial batch must have failed records")
        return replace(self, state=target)


@dataclass(frozen=True, slots=True)
class ProcessingAttempt:
    attempt_id: str
    batch_id: str
    processing_version: str
    state: ProcessingAttemptState = ProcessingAttemptState.CREATED
    retry_of_attempt_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_information: str | None = None
    counters: BatchCounters = field(default_factory=BatchCounters)

    def __post_init__(self) -> None:
        require_id(self.attempt_id, "attempt_id")
        require_id(self.batch_id, "batch_id")
        require_id(self.processing_version, "processing_version")
        if not isinstance(self.state, ProcessingAttemptState):
            raise InvalidValueError("state must be a ProcessingAttemptState")
        if self.retry_of_attempt_id is not None:
            require_id(self.retry_of_attempt_id, "retry_of_attempt_id")
            if self.retry_of_attempt_id == self.attempt_id:
                raise InvalidValueError("an attempt cannot retry itself")
        if self.started_at is not None:
            object.__setattr__(self, "started_at", require_utc(self.started_at, "started_at"))
        if self.ended_at is not None:
            object.__setattr__(self, "ended_at", require_utc(self.ended_at, "ended_at"))
        object.__setattr__(self, "error_information", normalize_text(self.error_information, "error_information", allow_empty=True))

    def transition_to(self, target: ProcessingAttemptState, *, at: datetime | None = None, error: str | None = None) -> "ProcessingAttempt":
        if not isinstance(target, ProcessingAttemptState):
            raise InvalidValueError("target must be a ProcessingAttemptState")
        allowed = {
            ProcessingAttemptState.CREATED: {ProcessingAttemptState.RUNNING},
            ProcessingAttemptState.RUNNING: {
                ProcessingAttemptState.COMPLETED,
                ProcessingAttemptState.FAILED,
                ProcessingAttemptState.TIMED_OUT,
                ProcessingAttemptState.CANCELLED,
            },
            ProcessingAttemptState.COMPLETED: set(),
            ProcessingAttemptState.FAILED: set(),
            ProcessingAttemptState.TIMED_OUT: set(),
            ProcessingAttemptState.CANCELLED: set(),
        }
        if target not in allowed[self.state]:
            raise InvalidTransitionError(f"illegal attempt transition {self.state.value} -> {target.value}")
        started_at = self.started_at
        ended_at = self.ended_at
        if target is ProcessingAttemptState.RUNNING:
            if at is None:
                raise InvalidValueError("running transition requires a timestamp")
            started_at = require_utc(at, "started_at")
        elif target in {
            ProcessingAttemptState.COMPLETED,
            ProcessingAttemptState.FAILED,
            ProcessingAttemptState.TIMED_OUT,
            ProcessingAttemptState.CANCELLED,
        }:
            if at is None:
                raise InvalidValueError("terminal attempt transition requires a timestamp")
            ended_at = require_utc(at, "ended_at")
            if started_at is None:
                raise InvalidTransitionError("an attempt cannot finish before it starts")
            if ended_at < started_at:
                raise InvalidValueError("ended_at cannot precede started_at")
        return replace(self, state=target, started_at=started_at, ended_at=ended_at, error_information=error)


@dataclass(frozen=True, slots=True)
class RawRecord:
    raw_record_id: str
    source_id: str
    batch_id: str
    source_record_id: str
    schema_version: str
    payload: Mapping[str, Any]
    content_fingerprint: str
    accepted_at: datetime
    invalid_reason: str | None = None
    supersedes_raw_record_id: str | None = None

    def __post_init__(self) -> None:
        require_id(self.raw_record_id, "raw_record_id")
        require_id(self.source_id, "source_id")
        require_id(self.batch_id, "batch_id")
        require_id(self.source_record_id, "source_record_id")
        require_id(self.schema_version, "schema_version")
        require_fingerprint(self.content_fingerprint, "content_fingerprint")
        object.__setattr__(self, "accepted_at", require_utc(self.accepted_at, "accepted_at"))
        if not isinstance(self.payload, Mapping):
            raise InvalidValueError("payload must be a mapping")
        object.__setattr__(self, "payload", freeze_mapping(self.payload))
        object.__setattr__(self, "invalid_reason", normalize_text(self.invalid_reason, "invalid_reason", allow_empty=True))
        if self.supersedes_raw_record_id is not None:
            require_id(self.supersedes_raw_record_id, "supersedes_raw_record_id")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    validation_id: str
    raw_record_id: str
    batch_id: str
    schema_version: str
    validation_version: str
    status: str
    errors: tuple[Mapping[str, str], ...] = ()
    validated_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.validation_id, "validation_id"), (self.raw_record_id, "raw_record_id"),
                            (self.batch_id, "batch_id"), (self.schema_version, "schema_version"),
                            (self.validation_version, "validation_version")):
            require_id(value, name)
        if self.status not in {"VALID", "INVALID"}:
            raise InvalidValueError("validation status must be VALID or INVALID")
        if not isinstance(self.errors, tuple):
            raise InvalidValueError("validation errors must be a tuple")
        normalized = tuple(freeze_mapping(error) for error in self.errors)
        object.__setattr__(self, "errors", normalized)
        if self.status == "VALID" and normalized:
            raise InvalidValueError("valid results cannot contain errors")
        if self.status == "INVALID" and not normalized:
            raise InvalidValueError("invalid results require errors")
        if self.validated_at is not None:
            object.__setattr__(self, "validated_at", require_utc(self.validated_at, "validated_at"))


@dataclass(frozen=True, slots=True)
class CanonicalTransaction:
    canonical_id: str
    source_id: str
    raw_record_id: str
    source_record_id: str
    occurred_at: datetime
    amount: Decimal | str | int
    currency: str
    direction: Direction
    normalization_version: str
    canonical_version: int
    canonical_fingerprint: str
    created_at: datetime
    transaction_type: str | None = None
    account_reference: str | None = None
    transaction_reference: str | None = None
    description: str | None = None
    transaction_status: str | None = None
    supersedes_canonical_id: str | None = None

    def __post_init__(self) -> None:
        require_id(self.canonical_id, "canonical_id")
        require_id(self.source_id, "source_id")
        require_id(self.raw_record_id, "raw_record_id")
        require_id(self.source_record_id, "source_record_id")
        object.__setattr__(self, "occurred_at", require_utc(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(self, "amount", require_amount(self.amount))
        object.__setattr__(self, "currency", require_currency(self.currency))
        if not isinstance(self.direction, Direction):
            raise InvalidValueError("direction must be CREDIT or DEBIT")
        require_id(self.normalization_version, "normalization_version")
        if not isinstance(self.canonical_version, int) or self.canonical_version < 1:
            raise InvalidValueError("canonical_version must be positive")
        require_fingerprint(self.canonical_fingerprint, "canonical_fingerprint")
        if self.supersedes_canonical_id is not None:
            require_id(self.supersedes_canonical_id, "supersedes_canonical_id")
            if self.supersedes_canonical_id == self.canonical_id:
                raise InvalidValueError("canonical transaction cannot supersede itself")
        for name in ("transaction_type", "account_reference", "transaction_reference", "description", "transaction_status"):
            object.__setattr__(self, name, normalize_text(getattr(self, name), name, allow_empty=True))

    def semantic_payload(self) -> dict[str, object]:
        """Return the fixed field order used as input to later identity generation."""

        return {
            "occurred_at": self.occurred_at.isoformat(),
            "amount": format(self.amount, "f"),
            "currency": self.currency,
            "direction": self.direction.value,
            "transaction_type": self.transaction_type,
            "account_reference": self.account_reference,
            "transaction_reference": self.transaction_reference,
            "description": self.description,
            "transaction_status": self.transaction_status,
        }


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    candidate_id: str
    source_a_canonical_id: str
    source_b_canonical_id: str
    eligible_rule_ids: tuple[str, ...]
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.candidate_id, "candidate_id")
        require_id(self.source_a_canonical_id, "source_a_canonical_id")
        require_id(self.source_b_canonical_id, "source_b_canonical_id")
        if self.source_a_canonical_id == self.source_b_canonical_id:
            raise InvalidValueError("candidate sides must identify distinct source records")
        if not self.eligible_rule_ids or any(not require_id(rule_id, "rule_id") for rule_id in self.eligible_rule_ids):
            raise InvalidValueError("candidate must contain at least one eligible rule")
        object.__setattr__(self, "eligible_rule_ids", tuple(self.eligible_rule_ids))
        object.__setattr__(self, "evidence", freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class Reconciliation:
    reconciliation_id: str
    batch_id: str
    source_a_record_id: str | None
    source_b_record_id: str | None
    reconciliation_version: int
    rule_version: str
    evidence: Mapping[str, Any]
    state: ReconciliationState = ReconciliationState.CREATED
    outcome: ReconciliationOutcome | None = None
    supersedes_reconciliation_id: str | None = None
    resolution_id: str | None = None
    raw_record_id: str | None = None

    def __post_init__(self) -> None:
        require_id(self.reconciliation_id, "reconciliation_id")
        require_id(self.batch_id, "batch_id")
        require_id(self.rule_version, "rule_version")
        if not isinstance(self.state, ReconciliationState):
            raise InvalidValueError("state must be a ReconciliationState")
        if self.outcome is not None and not isinstance(self.outcome, ReconciliationOutcome):
            raise InvalidValueError("outcome must be a ReconciliationOutcome")
        if self.raw_record_id is not None:
            require_id(self.raw_record_id, "raw_record_id")
        if self.source_a_record_id is None and self.source_b_record_id is None and self.raw_record_id is None:
            raise InvalidValueError("reconciliation must identify a canonical or raw record")
        if self.source_a_record_id is not None:
            require_id(self.source_a_record_id, "source_a_record_id")
        if self.source_b_record_id is not None:
            require_id(self.source_b_record_id, "source_b_record_id")
        if self.source_a_record_id is not None and self.source_a_record_id == self.source_b_record_id:
            raise InvalidValueError("source A and source B records must be distinct")
        if not isinstance(self.reconciliation_version, int) or self.reconciliation_version < 1:
            raise InvalidValueError("reconciliation_version must be positive")
        if self.supersedes_reconciliation_id is not None:
            require_id(self.supersedes_reconciliation_id, "supersedes_reconciliation_id")
            if self.supersedes_reconciliation_id == self.reconciliation_id:
                raise InvalidValueError("reconciliation cannot supersede itself")
        if self.resolution_id is not None:
            require_id(self.resolution_id, "resolution_id")
        object.__setattr__(self, "evidence", freeze_mapping(self.evidence))
        if self.state in {ReconciliationState.CREATED, ReconciliationState.EVALUATING} and self.outcome is not None:
            raise InvalidValueError("created/evaluating reconciliation cannot have an outcome")
        if self.state in {
            ReconciliationState.MATCHED,
            ReconciliationState.MISMATCHED,
            ReconciliationState.UNMATCHED_A,
            ReconciliationState.UNMATCHED_B,
            ReconciliationState.AMBIGUOUS,
            ReconciliationState.DUPLICATE,
            ReconciliationState.INVALID,
        } and self.outcome is not ReconciliationOutcome(self.state.value):
            raise InvalidValueError("terminal reconciliation state must match its outcome")
        if self.outcome is ReconciliationOutcome.INVALID:
            if self.raw_record_id is None or self.source_a_record_id is not None or self.source_b_record_id is not None:
                raise InvalidValueError("INVALID reconciliation requires raw-only lineage")
        elif self.state in {
            ReconciliationState.MATCHED, ReconciliationState.MISMATCHED,
            ReconciliationState.UNMATCHED_A, ReconciliationState.UNMATCHED_B,
            ReconciliationState.AMBIGUOUS, ReconciliationState.DUPLICATE,
        } and self.source_a_record_id is None and self.source_b_record_id is None:
            raise InvalidValueError("canonical reconciliation outcome requires canonical lineage")
        if self.state is ReconciliationState.RESOLVED and self.outcome not in {
            ReconciliationOutcome.MISMATCHED,
            ReconciliationOutcome.AMBIGUOUS,
        }:
            raise InvalidValueError("only mismatched or ambiguous reconciliations can be resolved")
        if self.state is ReconciliationState.RESOLVED and self.resolution_id is None:
            raise InvalidValueError("resolved reconciliation requires resolution_id")

    def transition_to(self, target: ReconciliationState, *, outcome: ReconciliationOutcome | None = None, resolution_id: str | None = None) -> "Reconciliation":
        if not isinstance(target, ReconciliationState):
            raise InvalidValueError("target must be a ReconciliationState")
        if self.state is ReconciliationState.CREATED and target is ReconciliationState.EVALUATING:
            if outcome is not None:
                raise InvalidValueError("evaluating reconciliation cannot have an outcome")
            return replace(self, state=target)
        if self.state is ReconciliationState.EVALUATING and target in {
            ReconciliationState.MATCHED,
            ReconciliationState.MISMATCHED,
            ReconciliationState.UNMATCHED_A,
            ReconciliationState.UNMATCHED_B,
            ReconciliationState.AMBIGUOUS,
            ReconciliationState.DUPLICATE,
            ReconciliationState.INVALID,
        }:
            expected = ReconciliationOutcome(target.value)
            if outcome is not None and outcome is not expected:
                raise InvalidTransitionError("state and outcome do not agree")
            if expected is ReconciliationOutcome.INVALID and self.raw_record_id is None:
                # Legacy callers may have carried the invalid source identifier
                # in a canonical slot; normalize it to the explicit raw lineage.
                raw_id = self.source_a_record_id or self.source_b_record_id
                return replace(self, source_a_record_id=None, source_b_record_id=None,
                               raw_record_id=raw_id, state=target, outcome=expected)
            return replace(self, state=target, outcome=expected)
        if self.state in {ReconciliationState.MISMATCHED, ReconciliationState.AMBIGUOUS} and target is ReconciliationState.RESOLVED:
            if not resolution_id:
                raise InvalidValueError("resolution_id is required to resolve a reconciliation")
            return replace(self, state=target, resolution_id=require_id(resolution_id, "resolution_id"))
        raise InvalidTransitionError(f"illegal reconciliation transition {self.state.value} -> {target.value}")


@dataclass(frozen=True, slots=True)
class Discrepancy:
    discrepancy_id: str
    reconciliation_id: str
    reason: str
    state: DiscrepancyState = DiscrepancyState.OPEN

    def __post_init__(self) -> None:
        require_id(self.discrepancy_id, "discrepancy_id")
        require_id(self.reconciliation_id, "reconciliation_id")
        if not isinstance(self.state, DiscrepancyState):
            raise InvalidValueError("state must be a DiscrepancyState")
        reason = normalize_text(self.reason, "reason")
        if not reason:
            raise InvalidValueError("reason must not be empty")
        object.__setattr__(self, "reason", reason)

    def transition_to(self, target: DiscrepancyState) -> "Discrepancy":
        if not isinstance(target, DiscrepancyState):
            raise InvalidValueError("target must be a DiscrepancyState")
        allowed = {
            DiscrepancyState.OPEN: {DiscrepancyState.DEFERRED, DiscrepancyState.RESOLVED, DiscrepancyState.REJECTED},
            DiscrepancyState.DEFERRED: {DiscrepancyState.RESOLVED, DiscrepancyState.REJECTED},
            DiscrepancyState.RESOLVED: set(),
            DiscrepancyState.REJECTED: set(),
        }
        if target not in allowed[self.state]:
            raise InvalidTransitionError(f"illegal discrepancy transition {self.state.value} -> {target.value}")
        return replace(self, state=target)


@dataclass(frozen=True, slots=True)
class Resolution:
    resolution_id: str
    discrepancy_id: str
    reconciliation_id: str
    resolution_type: ResolutionType
    actor: str
    reason: str
    created_at: datetime
    evidence: Mapping[str, Any] = field(default_factory=dict)
    rule_version: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.resolution_id, "resolution_id"),
            (self.discrepancy_id, "discrepancy_id"),
            (self.reconciliation_id, "reconciliation_id"),
            (self.actor, "actor"),
        ):
            require_id(value, name)
        reason = normalize_text(self.reason, "reason")
        if not reason:
            raise InvalidValueError("reason must not be empty")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        if not isinstance(self.resolution_type, ResolutionType):
            raise InvalidValueError("resolution_type must be a ResolutionType")
        if self.resolution_type is ResolutionType.MANUAL_APPROVED and self.actor != "reconciliation_operator":
            raise InvalidValueError("manual resolutions require reconciliation_operator")
        if self.rule_version is not None:
            require_id(self.rule_version, "rule_version")
        object.__setattr__(self, "evidence", freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    entity_type: str
    entity_id: str
    event_type: AuditEventType
    actor: str
    timestamp: datetime
    sequence: int
    stage_version: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    previous_state: str | None = None
    new_state: str | None = None
    batch_id: str | None = None
    attempt_id: str | None = None
    record_id: str | None = None
    reconciliation_id: str | None = None
    causation_event_id: str | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.event_id, "event_id"), (self.entity_type, "entity_type"), (self.entity_id, "entity_id"), (self.actor, "actor"), (self.stage_version, "stage_version")):
            require_id(value, name)
        if not isinstance(self.event_type, AuditEventType):
            raise InvalidValueError("event_type must be an AuditEventType")
        object.__setattr__(self, "timestamp", require_utc(self.timestamp, "timestamp"))
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise InvalidValueError("sequence must be positive")
        for value, name in ((self.batch_id, "batch_id"), (self.attempt_id, "attempt_id"), (self.record_id, "record_id"), (self.reconciliation_id, "reconciliation_id"), (self.causation_event_id, "causation_event_id")):
            if value is not None:
                require_id(value, name)
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
