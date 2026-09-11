"""Supported operator pipeline runner (EMM-110).

This is the published, product-owned way to advance stored batches through the
processing stages. `Architecture.md` §39/§2157 keep processing out of the HTTP
surface, so the service is the data plane and this runner is the processing
plane: ``docs/service.md`` documents it as the supported operator entrypoint.

Design rules the runner guarantees:

* **Explicit selection.** Batches are selected by id or by state; there is no
  implicit "process everything".
* **Idempotent re-run.** Every stage is deterministic and idempotent, and the
  batch counters are *recomputed* from authoritative rows rather than
  incremented, so a second run over unchanged data writes no new row and
  returns the same counters.
* **Explicit partial failure.** A run records a ``processing_attempts`` row with
  an explicit terminal state; a batch ends ``COMPLETED`` only when every record
  reached a terminal outcome, and ``PARTIAL``/``FAILED`` otherwise.
* **No silent repair.** A ``COMPLETED`` batch is not reopened. A late arrival
  arrives as a new batch; matching re-evaluates and supersedes the affected
  decision under LA-1 while the earlier batch summary stays historical.

Usage::

    PYTHONPATH=src python3 -m ledger.pipeline list --database ledger.sqlite3 [--state RECEIVED]
    PYTHONPATH=src python3 -m ledger.pipeline process --database ledger.sqlite3 --batch <id>
    PYTHONPATH=src python3 -m ledger.pipeline process --database ledger.sqlite3 --state VALIDATED
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sys
import uuid
from typing import Any, Iterable, Sequence

from .candidates import CandidateGenerationService
from .domain import BatchCounters, BatchState, ProcessingAttempt, ProcessingAttemptState
from .identity import IdentityService
from .matching import MatchingService
from .normalization import NormalizationService
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase
from .reconciliation import ReconciliationService
from .validation import ValidationService

PIPELINE_VERSION = "pipeline_v1"
VALIDATION_VERSION = "validation_v1"

# States an operator run may pick up. COMPLETED and REJECTED are deliberately
# excluded: completed batches are historical summaries and are never reopened.
PENDING_STATES: tuple[BatchState, ...] = (
    BatchState.RECEIVED,
    BatchState.VALIDATING,
    BatchState.VALIDATED,
    BatchState.FAILED,
    BatchState.PARTIAL,
)


class PipelineError(RuntimeError):
    """The runner refused to proceed (operator error)."""


@dataclass(slots=True)
class BatchRun:
    """Outcome of one batch in one operator run."""

    batch_id: str
    status: str
    state: str
    attempt_id: str | None = None
    counters: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    outcomes: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "state": self.state,
            "attempt_id": self.attempt_id,
            "counters": self.counters,
            "outcomes": self.outcomes,
            "error": self.error,
        }


def _record_outcomes(database: LedgerDatabase, batch_ids: Sequence[str]) -> dict[str, dict[str, str]]:
    """Map every raw record in the given batches to its terminal outcome.

    Scoped to the selected batches but resolved against the *global* decision
    graph, because one decision row can pair a record from this batch with a
    record from another batch.
    """
    placeholders = ",".join("?" for _ in batch_ids)
    raw_ids: set[str] = set()
    canonical_to_raw: dict[str, str] = {}
    rows = database.connection.execute(
        f"SELECT raw_record_id FROM raw_records WHERE batch_id IN ({placeholders})", tuple(batch_ids)  # nosec B608 - placeholders count bound "?" markers
    ).fetchall()
    for row in rows:
        raw_ids.add(row["raw_record_id"])
    if not raw_ids:
        return {}
    raw_placeholders = ",".join("?" for _ in raw_ids)
    for row in database.connection.execute(
        f"SELECT canonical_id, raw_record_id FROM canonical_transactions WHERE raw_record_id IN ({raw_placeholders})",  # nosec B608 - placeholders count bound "?" markers
        tuple(raw_ids),
    ).fetchall():
        canonical_to_raw[row["canonical_id"]] = row["raw_record_id"]

    canonical_outcome: dict[str, str] = {}
    raw_outcome: dict[str, str] = {}
    for row in database.connection.execute(
        "SELECT outcome, source_a_record_id, source_b_record_id, raw_record_id FROM reconciliations "
        "WHERE outcome IS NOT NULL AND supersedes_reconciliation_id IS NULL"
    ).fetchall():
        for column in ("source_a_record_id", "source_b_record_id"):
            if row[column] in canonical_to_raw:
                canonical_outcome[row[column]] = row["outcome"]
        if row["raw_record_id"] in raw_ids:
            raw_outcome[row["raw_record_id"]] = row["outcome"]

    outcomes: dict[str, dict[str, str]] = {}
    for raw_id in sorted(raw_ids):
        validation = database.validation_results.get_for_raw(raw_id, VALIDATION_VERSION)
        if validation is not None and validation.status == "INVALID":
            outcomes[raw_id] = {"outcome": "INVALID"}
            continue
        canonical_id = None
        raw = database.raw_records.get(raw_id)
        if raw is not None and raw.invalid_reason:
            outcomes[raw_id] = {"outcome": "INVALID"}
            continue
        for candidate, source_raw in canonical_to_raw.items():
            if source_raw == raw_id:
                canonical_id = candidate
                break
        outcome = canonical_outcome.get(canonical_id) or raw_outcome.get(raw_id)
        if outcome is not None:
            outcomes[raw_id] = {"outcome": outcome}
    return outcomes


def _derive_counters(batch: Any, outcomes: dict[str, dict[str, str]]) -> BatchCounters:
    """Recompute the outcome counters from authoritative rows.

    `Architecture.md` §"batch counters" makes these authoritative summaries of
    record outcomes: ``processed_count = matched + mismatched + unmatched +
    ambiguous + duplicate + invalid``. Recomputing (rather than incrementing)
    makes a repeated run idempotent and keeps that identity true by construction.
    """
    matched = mismatched = unmatched = ambiguous = duplicate = invalid = 0
    for entry in outcomes.values():
        outcome = entry["outcome"]
        if outcome == "MATCHED":
            matched += 1
        elif outcome == "MISMATCHED":
            mismatched += 1
        elif outcome in {"UNMATCHED_A", "UNMATCHED_B"}:
            unmatched += 1
        elif outcome == "AMBIGUOUS":
            ambiguous += 1
        elif outcome == "DUPLICATE":
            duplicate += 1
        elif outcome == "INVALID":
            invalid += 1
    counters = batch.counters
    return BatchCounters(
        received_count=counters.received_count,
        accepted_count=counters.accepted_count,
        rejected_input_count=counters.rejected_input_count,
        invalid_count=invalid,
        processed_count=matched + mismatched + unmatched + ambiguous + duplicate + invalid,
        matched_count=matched,
        mismatched_count=mismatched,
        unmatched_count=unmatched,
        ambiguous_count=ambiguous,
        duplicate_count=duplicate,
        failed_count=counters.failed_count,
    )


def select_batches(
    database: LedgerDatabase,
    *,
    batch_ids: Iterable[str] | None = None,
    states: Iterable[BatchState] | None = None,
) -> list[str]:
    """Select batches deterministically: explicit ids, or ids in the given states."""
    if batch_ids:
        selected: list[str] = []
        for batch_id in batch_ids:
            if database.batches.get(batch_id) is None:
                raise PipelineError(f"batch {batch_id!r} does not exist")
            selected.append(batch_id)
        return sorted(selected)
    allowed = tuple(states) if states else PENDING_STATES
    placeholders = ",".join("?" for _ in allowed)
    rows = database.connection.execute(
        f"SELECT batch_id FROM batches WHERE state IN ({placeholders}) ORDER BY batch_id",  # nosec B608 - placeholders count bound "?" markers
        tuple(state.value for state in allowed),
    ).fetchall()
    return [row["batch_id"] for row in rows]


def process_batches(
    database: LedgerDatabase,
    batch_ids: Sequence[str],
    *,
    evaluated_at: datetime | None = None,
    telemetry: TelemetrySink | None = None,
    attempt_ids: dict[str, str] | None = None,
) -> list[BatchRun]:
    """Advance the selected batches through the processing stages.

    Stages run in the documented order (Architecture §6): validation,
    normalization, identity, candidate generation, matching, invalid
    reconciliation. Global stages run once over the whole selection because
    matching pairs records across batches.
    """
    timestamp = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    runs: dict[str, BatchRun] = {}
    active: list[str] = []
    attempts: dict[str, ProcessingAttempt] = {}

    for batch_id in sorted(batch_ids):
        batch = database.batches.get(batch_id)
        if batch is None:
            raise PipelineError(f"batch {batch_id!r} does not exist")
        if batch.state in {BatchState.COMPLETED, BatchState.REJECTED}:
            runs[batch_id] = BatchRun(batch_id, "skipped", batch.state.value,
                                      counters=_counters_dict(batch.counters))
            continue
        attempt_id = (attempt_ids or {}).get(batch_id) or f"attempt:{uuid.uuid4().hex}"
        attempt = ProcessingAttempt(attempt_id, batch_id, PIPELINE_VERSION)
        database.processing_attempts.save(attempt)
        attempt = database.processing_attempts.transition_with_audit(
            attempt, ProcessingAttemptState.RUNNING, _attempt_event(attempt, ProcessingAttemptState.RUNNING, timestamp),
            at=timestamp,
        )
        attempts[batch_id] = attempt
        active.append(batch_id)

    if active:
        try:
            _run_stages(database, active, timestamp, telemetry)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            for batch_id in active:
                attempt = attempts[batch_id]
                failed = database.processing_attempts.transition_with_audit(
                    attempt, ProcessingAttemptState.FAILED, _attempt_event(attempt, ProcessingAttemptState.FAILED, timestamp, str(exc)),
                    at=timestamp, error=str(exc),
                )
                batch = database.batches.get(batch_id)
                state = _mark_failed(database, batch, timestamp)
                runs[batch_id] = BatchRun(batch_id, "failed", state, attempt_id=failed.attempt_id,
                                          counters=_counters_dict(batch.counters), error=str(exc))
                _emit(telemetry, "ledger.pipeline.batch_failed",
                      {"batch_id": batch_id, "attempt_id": failed.attempt_id, "error": type(exc).__name__})
            return [runs[batch_id] for batch_id in sorted(runs)]

        for batch_id in active:
            attempt = attempts[batch_id]
            outcomes = _record_outcomes(database, [batch_id])
            batch = database.batches.get(batch_id)
            counters = _derive_counters(batch, outcomes)
            batch = database.batches.update_counters(batch_id, counters)
            target = BatchState.PARTIAL if counters.failed_count else BatchState.COMPLETED
            state = _transition_batch(database, batch, target, timestamp)
            completed = database.processing_attempts.transition_with_audit(
                attempt, ProcessingAttemptState.COMPLETED,
                _attempt_event(attempt, ProcessingAttemptState.COMPLETED, timestamp), at=timestamp,
            )
            summary = _outcome_summary(outcomes)
            runs[batch_id] = BatchRun(batch_id, "processed", state, attempt_id=completed.attempt_id,
                                      counters=_counters_dict(counters), outcomes=summary)
            _emit(telemetry, "ledger.pipeline.batch_processed",
                  {"batch_id": batch_id, "attempt_id": completed.attempt_id, "state": state,
                   "outcome_counts": summary})
    return [runs[batch_id] for batch_id in sorted(runs)]


def _run_stages(
    database: LedgerDatabase, batch_ids: Sequence[str], timestamp: datetime, telemetry: TelemetrySink | None
) -> None:
    validation = ValidationService(database, telemetry=telemetry)
    for batch_id in batch_ids:
        validation.validate_batch(batch_id)
    normalization = NormalizationService(database, telemetry=telemetry)
    raw_ids: list[str] = []
    for batch_id in batch_ids:
        raw_ids.extend(row.raw_record_id for row in database.raw_records.list_for_batch(batch_id))
    created_at = timestamp
    for raw_id in raw_ids:
        normalization.normalize_record(raw_id, created_at=created_at)
    identity = IdentityService(database, telemetry=telemetry)
    for transaction in database.canonical_transactions.list_all():
        identity.identify(transaction)
    CandidateGenerationService(database, telemetry=telemetry).generate_all()
    MatchingService(database).evaluate(evaluated_at=timestamp)
    reconciliation = ReconciliationService(database, telemetry=telemetry)
    for batch_id in batch_ids:
        for raw in database.raw_records.list_for_batch(batch_id):
            result = database.validation_results.get_for_raw(raw.raw_record_id, VALIDATION_VERSION)
            if result is not None and result.status == "INVALID":
                reconciliation.reconcile_invalid(
                    raw.raw_record_id, batch_id=raw.batch_id,
                    evidence={"validation": "INVALID", "validation_version": result.validation_version},
                )


def _transition_batch(
    database: LedgerDatabase, batch: Any, target: BatchState, timestamp: datetime
) -> str:
    """Walk a batch to its terminal state through only legal transitions."""
    if batch.state is BatchState.RECEIVED:
        raise PipelineError("validation did not reach a terminal state for the batch")
    # A retry of a previously failed or partial batch is explicitly permitted by
    # the state machine; a fresh batch is not a retry.
    retry = batch.state in {BatchState.FAILED, BatchState.PARTIAL}
    if target is BatchState.COMPLETED:
        batch = database.batches.transition_with_audit(
            batch, BatchState.PROCESSING, _batch_event(batch, BatchState.PROCESSING, timestamp),
            retry=retry, attempt_created=True,
        )
        batch = database.batches.transition_with_audit(
            batch, BatchState.COMPLETED, _batch_event(batch, BatchState.COMPLETED, timestamp)
        )
        return batch.state.value
    batch = database.batches.transition_with_audit(
        batch, BatchState.PROCESSING, _batch_event(batch, BatchState.PROCESSING, timestamp),
        retry=retry, attempt_created=True,
    )
    batch = database.batches.transition_with_audit(
        batch, target, _batch_event(batch, target, timestamp), retry=retry
    )
    return batch.state.value


def _mark_failed(database: LedgerDatabase, batch: Any, timestamp: datetime) -> str:
    """Record a stage failure on the batch without inventing progress.

    * ``VALIDATED`` means validation completed and a later stage failed, so the
      batch legally enters ``PROCESSING`` and then ``FAILED``.
    * ``PROCESSING`` (mid-transition) becomes ``PARTIAL`` when records already
      failed, otherwise ``FAILED``.
    * ``RECEIVED``/``VALIDATING`` stay unchanged: validation itself did not
      finish, so claiming any later state would be false. The batch remains
      selectable for retry and the failure is carried by the attempt row.
    """
    if batch.state is BatchState.VALIDATED:
        batch = database.batches.transition_with_audit(
            batch, BatchState.PROCESSING, _batch_event(batch, BatchState.PROCESSING, timestamp),
            attempt_created=True,
        )
        batch = database.batches.transition_with_audit(
            batch, BatchState.FAILED, _batch_event(batch, BatchState.FAILED, timestamp)
        )
        return batch.state.value
    if batch.state is BatchState.PROCESSING:
        target = BatchState.PARTIAL if batch.counters.failed_count else BatchState.FAILED
        batch = database.batches.transition_with_audit(
            batch, target, _batch_event(batch, target, timestamp), retry=True
        )
        return batch.state.value
    return batch.state.value


def _batch_event(batch: Any, target: BatchState, timestamp: datetime) -> Any:
    import hashlib

    from .domain import AuditEvent, AuditEventType

    digest = hashlib.sha256(
        f"BATCH_STATE_CHANGED:{batch.batch_id}:{batch.state.value}:{target.value}:{PIPELINE_VERSION}".encode()
    ).hexdigest()
    return AuditEvent(
        "audit:" + digest, "batch", batch.batch_id, AuditEventType.BATCH_STATE_CHANGED, "system", timestamp, 1,
        PIPELINE_VERSION, previous_state=batch.state.value, new_state=target.value, batch_id=batch.batch_id,
    )


def _attempt_event(attempt: ProcessingAttempt, target: ProcessingAttemptState, timestamp: datetime, error: str | None = None) -> Any:
    import hashlib

    from .domain import AuditEvent, AuditEventType

    digest = hashlib.sha256(
        f"PROCESSING_ATTEMPT:{attempt.attempt_id}:{attempt.state.value}:{target.value}:{error or ''}".encode()
    ).hexdigest()
    return AuditEvent(
        "audit:" + digest, "processing_attempt", attempt.attempt_id,
        AuditEventType.BATCH_STATE_CHANGED, "system", timestamp, 1, PIPELINE_VERSION,
        metadata={"attempt_state": target.value, "error": error}, batch_id=attempt.batch_id,
    )


def _emit(telemetry: TelemetrySink | None, name: str, attributes: dict[str, Any]) -> None:
    if telemetry is not None:
        telemetry.emit(
            TelemetryEvent(name, CorrelationContext(batch_id=attributes.get("batch_id")), attributes)
        )


def _counters_dict(counters: BatchCounters) -> dict[str, int]:
    return {name: getattr(counters, name) for name in BatchCounters.__dataclass_fields__}


def _outcome_summary(outcomes: dict[str, dict[str, str]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for entry in outcomes.values():
        summary[entry["outcome"]] = summary.get(entry["outcome"], 0) + 1
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger.pipeline", description="LEDGER operator pipeline runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list selectable batches")
    list_parser.add_argument("--database", required=True)
    list_parser.add_argument("--state", action="append", default=None)

    process_parser = subparsers.add_parser("process", help="advance batches through the pipeline")
    process_parser.add_argument("--database", required=True)
    process_parser.add_argument("--batch", action="append", default=None)
    process_parser.add_argument("--state", action="append", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    database = LedgerDatabase(arguments.database)
    try:
        if arguments.command == "list":
            states = [BatchState(item.upper()) for item in (arguments.state or [])]
            batch_ids = select_batches(database, states=states or None)
            print(json.dumps({"batches": batch_ids, "count": len(batch_ids)}, indent=2))
            return 0
        if arguments.state and arguments.batch:
            print(json.dumps({"ok": False, "error": "--state and --batch are mutually exclusive"}, indent=2),
                  file=sys.stderr)
            return 1
        states = [BatchState(item.upper()) for item in (arguments.state or [])]
        batch_ids = select_batches(database, batch_ids=arguments.batch, states=states or None)
        if not batch_ids:
            print(json.dumps({"ok": True, "selected": 0, "runs": []}, indent=2))
            return 0
        runs = process_batches(database, batch_ids)
    except (PipelineError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        database.close()
    failures = [run for run in runs if run.status == "failed"]
    print(json.dumps({"ok": not failures, "selected": len(batch_ids), "runs": [run.as_dict() for run in runs]},
                     indent=2, sort_keys=True))
    return 2 if failures else 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
