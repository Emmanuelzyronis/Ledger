"""Layer 11 discrepancy resolution and immutable audit orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

from .domain import (
    AuditEvent,
    AuditEventType,
    Discrepancy,
    DiscrepancyState,
    Reconciliation,
    ReconciliationState,
    Resolution,
    ResolutionType,
)
from .identity import canonical_json
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


RESOLUTION_STAGE_VERSION = "resolution_v1"


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    resolution: Resolution
    discrepancy: Discrepancy
    reconciliation: Reconciliation


class ResolutionService:
    """Apply one authorized, deterministic resolution to one open discrepancy."""

    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None) -> None:
        self.database = database
        self.telemetry = telemetry

    def resolve(
        self,
        discrepancy_id: str,
        resolution_type: ResolutionType,
        *,
        actor: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
        rule_version: str | None = None,
        created_at: datetime | None = None,
    ) -> ResolutionResult:
        """Resolve a discrepancy; retries return the original immutable result."""
        discrepancy = self.database.discrepancies.get(discrepancy_id)
        if discrepancy is None:
            raise ValueError("discrepancy does not exist")
        reconciliation = self.database.reconciliations.get(discrepancy.reconciliation_id)
        if reconciliation is None:
            raise ValueError("discrepancy reconciliation does not exist")
        if reconciliation.state not in {ReconciliationState.MISMATCHED, ReconciliationState.AMBIGUOUS}:
            raise ValueError("only mismatched or ambiguous reconciliations can be resolved")
        existing_for_discrepancy = self.database.connection.execute(
            "SELECT resolution_id FROM resolutions WHERE discrepancy_id = ?", (discrepancy_id,)
        ).fetchone()
        if existing_for_discrepancy is not None:
            return self._existing_result(self.database.resolutions.get(existing_for_discrepancy["resolution_id"]))  # type: ignore[arg-type]
        if resolution_type is ResolutionType.AUTOMATIC:
            if actor != "system" or not rule_version:
                raise PermissionError("automatic resolutions require system actor and rule_version")
        elif actor != "reconciliation_operator":
            raise PermissionError("resolution requires reconciliation_operator")

        digest = hashlib.sha256(canonical_json([
            discrepancy_id, reconciliation.reconciliation_id, resolution_type.value,
            actor, reason.strip(), evidence or {}, rule_version,
        ])).hexdigest()
        resolution_id = "resolution:" + digest
        existing = self.database.resolutions.get(resolution_id)
        if existing is not None:
            return self._existing_result(existing)
        timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        resolution = Resolution(resolution_id, discrepancy_id, reconciliation.reconciliation_id,
                                resolution_type, actor, reason, timestamp, evidence or {}, rule_version)
        terminal_state = DiscrepancyState.RESOLVED if resolution_type in {ResolutionType.AUTOMATIC, ResolutionType.MANUAL_APPROVED} else (
            DiscrepancyState.DEFERRED if resolution_type is ResolutionType.DEFERRED else DiscrepancyState.REJECTED
        )
        base = [resolution_id, discrepancy_id, reconciliation.reconciliation_id, resolution_type.value]
        discrepancy_event = self._event("discrepancy", discrepancy_id, base + ["discrepancy"], actor, timestamp,
                                         previous_state=discrepancy.state.value, new_state=terminal_state.value,
                                         batch_id=reconciliation.batch_id, reconciliation_id=reconciliation.reconciliation_id)
        resolution_event = self._event("resolution", resolution_id, base + ["resolution"], actor, timestamp,
                                       batch_id=reconciliation.batch_id, reconciliation_id=reconciliation.reconciliation_id)
        if terminal_state is not DiscrepancyState.RESOLVED:
            self.database.resolutions.apply_terminal_with_audit(resolution, discrepancy, terminal_state, discrepancy_event, resolution_event)
            result = ResolutionResult(resolution, self.database.discrepancies.get(discrepancy_id), reconciliation)  # type: ignore[arg-type]
        else:
            next_id = "reconciliation:" + hashlib.sha256(canonical_json([reconciliation.reconciliation_id, resolution_id])).hexdigest()
            next_reconciliation = Reconciliation(next_id, reconciliation.batch_id, reconciliation.source_a_record_id,
                reconciliation.source_b_record_id, reconciliation.reconciliation_version + 1, reconciliation.rule_version,
                {**dict(reconciliation.evidence), "resolution_id": resolution_id, "resolution_type": resolution_type.value},
                ReconciliationState.RESOLVED, reconciliation.outcome, reconciliation.reconciliation_id, resolution_id,
                reconciliation.raw_record_id)
            reconciliation_event = self._event("reconciliation", next_id, base + ["reconciliation"], actor, timestamp,
                                               previous_state=reconciliation.state.value, new_state=ReconciliationState.RESOLVED.value,
                                               batch_id=reconciliation.batch_id, reconciliation_id=next_id)
            self.database.resolutions.apply_with_audit(resolution, discrepancy, terminal_state, reconciliation,
                                                       next_reconciliation, discrepancy_event, reconciliation_event, resolution_event)
            result = ResolutionResult(resolution, self.database.discrepancies.get(discrepancy_id), next_reconciliation)  # type: ignore[arg-type]
        if self.telemetry:
            self.telemetry.emit(TelemetryEvent("ledger.resolution.applied", CorrelationContext(
                batch_id=reconciliation.batch_id, reconciliation_id=reconciliation.reconciliation_id),
                {"resolution_type": resolution_type.value, "discrepancy_state": terminal_state.value, "actor": actor}))
        return result

    def _existing_result(self, resolution: Resolution) -> ResolutionResult:
        discrepancy = self.database.discrepancies.get(resolution.discrepancy_id)
        reconciliation = self.database.reconciliations.get(resolution.reconciliation_id)
        if discrepancy is None or reconciliation is None:
            raise ValueError("resolution lineage is incomplete")
        rows = self.database.connection.execute("SELECT reconciliation_id FROM reconciliations WHERE resolution_id = ? ORDER BY reconciliation_version DESC", (resolution.resolution_id,)).fetchone()
        if rows:
            reconciliation = self.database.reconciliations.get(rows["reconciliation_id"]) or reconciliation
        return ResolutionResult(resolution, discrepancy, reconciliation)

    @staticmethod
    def _event(entity_type: str, entity_id: str, identity: list[str], actor: str, timestamp: datetime, **kwargs: Any) -> AuditEvent:
        event_id = "audit:" + hashlib.sha256(canonical_json(identity)).hexdigest()
        return AuditEvent(event_id, entity_type, entity_id, AuditEventType.RESOLUTION_APPLIED, actor, timestamp, 1,
                          RESOLUTION_STAGE_VERSION, metadata={"resolution_type": identity[3]}, **kwargs)


ResolutionEngine = ResolutionService
