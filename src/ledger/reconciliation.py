"""Layer 10 authoritative reconciliation persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from .domain import AuditEvent, AuditEventType, Reconciliation, ReconciliationOutcome, ReconciliationState, Discrepancy
from .identity import canonical_json
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


RECONCILIATION_STAGE_VERSION = "reconciliation_v1"


class ReconciliationService:
    """Persist deterministic terminal decisions, discrepancies, and evidence atomically."""

    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None) -> None:
        self.database = database
        self.telemetry = telemetry

    def persist_decision(
        self,
        *,
        batch_id: str,
        outcome: ReconciliationOutcome,
        evidence: dict[str, Any],
        source_a_record_id: str | None = None,
        source_b_record_id: str | None = None,
        raw_record_id: str | None = None,
        rule_version: str = "standard_v1",
        evaluated_at: datetime | None = None,
    ) -> Reconciliation:
        timestamp = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        existing, supersedes = self._resolve_version(
            source_a_record_id, source_b_record_id, raw_record_id, outcome, rule_version)
        if existing is not None:
            return existing
        version = supersedes.reconciliation_version + 1 if supersedes is not None else 1
        identity = [source_a_record_id, source_b_record_id, raw_record_id, outcome.value, rule_version,
                    supersedes.reconciliation_id if supersedes is not None else None]
        rec_id = "reconciliation:" + hashlib.sha256(canonical_json(identity)).hexdigest()
        decision_evidence = {**evidence, "outcome": outcome.value, "evaluated_at": timestamp.isoformat()}
        supersedes_reconciliation_id = None
        if supersedes is not None:
            supersedes_reconciliation_id = supersedes.reconciliation_id
            decision_evidence["supersedes_reconciliation_id"] = supersedes.reconciliation_id
            decision_evidence["superseded_scope"] = sorted(
                item for item in (supersedes.source_a_record_id, supersedes.source_b_record_id) if item)
        reconciliation = Reconciliation(rec_id, batch_id, source_a_record_id, source_b_record_id, version, rule_version,
                                        decision_evidence,
                                        ReconciliationState(outcome.value), outcome, supersedes_reconciliation_id,
                                        raw_record_id=raw_record_id)
        event_type = AuditEventType.DUPLICATE_DETECTED if outcome is ReconciliationOutcome.DUPLICATE else AuditEventType.MATCH_EVALUATED
        event_id = "audit:" + hashlib.sha256(canonical_json([rec_id, event_type.value])).hexdigest()
        event = AuditEvent(event_id, "reconciliation", rec_id, event_type, "system", timestamp, 1,
                           RECONCILIATION_STAGE_VERSION, metadata={"outcome": outcome.value, "rule_version": rule_version},
                           batch_id=batch_id, record_id=raw_record_id, reconciliation_id=rec_id)
        discrepancy = None
        discrepancy_event = None
        if outcome in {ReconciliationOutcome.MISMATCHED, ReconciliationOutcome.AMBIGUOUS}:
            discrepancy_id = "discrepancy:" + hashlib.sha256(canonical_json([rec_id, outcome.value, rule_version])).hexdigest()
            discrepancy = Discrepancy(discrepancy_id, rec_id, "amount, currency, or direction differs" if outcome is ReconciliationOutcome.MISMATCHED else "multiple candidates satisfy the highest applicable rule")
            discrepancy_event = AuditEvent("audit:" + hashlib.sha256(canonical_json([discrepancy_id, event_id])).hexdigest(), "discrepancy", discrepancy_id,
                                           AuditEventType.DISCREPANCY_CREATED, "system", timestamp, 1, RECONCILIATION_STAGE_VERSION,
                                           metadata={"reconciliation_id": rec_id, "outcome": outcome.value}, batch_id=batch_id, reconciliation_id=rec_id)
        with self.database.transaction():
            existing = self.database.reconciliations.get(rec_id)
            if existing is not None:
                return existing
            self.database.reconciliations.save(reconciliation)
            if discrepancy is not None:
                self.database.discrepancies.save(discrepancy)
            self.database.audit_events.append(event)
            if discrepancy_event is not None:
                self.database.audit_events.append(discrepancy_event)
        if self.telemetry:
            self.telemetry.emit(TelemetryEvent("ledger.reconciliation.completed", CorrelationContext(batch_id=batch_id, record_id=raw_record_id, reconciliation_id=rec_id), {"outcome": outcome.value, "rule_version": rule_version, "discrepancy_created": discrepancy is not None}))
        return reconciliation

    def _resolve_version(
        self,
        source_a_record_id: str | None,
        source_b_record_id: str | None,
        raw_record_id: str | None,
        outcome: ReconciliationOutcome,
        rule_version: str,
    ) -> tuple[Reconciliation | None, Reconciliation | None]:
        """Resolve idempotent replay vs. a new superseding version.

        Returns ``(existing, supersedes)``:

        * ``existing`` is the current decision with identical content, so a
          repeated evaluation returns it unchanged and creates no new version.
        * ``supersedes`` is the current decision whose participant scope is a
          subset of this decision's scope. A late arrival extends a previously
          decided scope with a new counterpart, so the prior version is linked
          and never rewritten (Architecture §28 / D-007).
        """
        participants = {item for item in (source_a_record_id, source_b_record_id) if item is not None}
        if not participants:
            return None, None
        candidates: list[Reconciliation] = []
        for row in self.database.reconciliations.find_current_for_participants(participants):
            row_participants = {item for item in (row.source_a_record_id, row.source_b_record_id) if item is not None}
            if not row_participants <= participants:
                continue
            if (
                row.source_a_record_id == source_a_record_id
                and row.source_b_record_id == source_b_record_id
                and row.raw_record_id == raw_record_id
                and row.outcome == outcome
                and row.rule_version == rule_version
            ):
                return row, None
            candidates.append(row)
        if not candidates:
            return None, None
        return None, max(candidates, key=lambda row: (row.reconciliation_version, row.reconciliation_id))

    def reconcile_invalid(self, raw_record_id: str, *, batch_id: str | None = None, evidence: dict[str, Any] | None = None) -> Reconciliation:
        raw = self.database.raw_records.get(raw_record_id)
        if raw is None:
            raise ValueError("raw record does not exist")
        return self.persist_decision(batch_id=batch_id or raw.batch_id, outcome=ReconciliationOutcome.INVALID,
                                     raw_record_id=raw_record_id, evidence=evidence or {"validation": "INVALID"})


ReconciliationEngine = ReconciliationService
