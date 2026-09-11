"""Read-only reporting projections derived from authoritative SQLite state."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from .persistence import LedgerDatabase


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return value


def _redact_export(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(term in str(k).casefold() for term in ("payload", "description", "secret", "token", "credential")) else _redact_export(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_export(v) for v in value]
    return value


class ReportingService:
    """Build disposable projections; this service never writes business tables."""

    def __init__(self, database: LedgerDatabase) -> None:
        self.database = database

    def _rows(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        rows = self.database.connection.execute(f"SELECT * FROM {table}{where}", params).fetchall()
        return [{key: _json_value(row[key]) for key in row.keys()} for row in rows]

    def batch_status(self, batch_id: str) -> dict[str, Any] | None:
        rows = self._rows("batches", " WHERE batch_id = ?", (batch_id,))
        if not rows:
            return None
        result = rows[0]
        counters = result.pop("counters_json", "{}")
        result["counters"] = json.loads(counters) if isinstance(counters, str) else counters
        return result

    def reconciliations(self, *, batch_id: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE batch_id = ?" if batch_id else ""
        return self._rows("reconciliations", where, (batch_id,) if batch_id else ())

    def discrepancies(self, *, batch_id: str | None = None) -> list[dict[str, Any]]:
        if batch_id:
            return self._rows("discrepancies", " WHERE reconciliation_id IN (SELECT reconciliation_id FROM reconciliations WHERE batch_id = ?)", (batch_id,))
        return self._rows("discrepancies", " ORDER BY discrepancy_id")

    def audit(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        return self._rows("audit_events", " WHERE entity_type = ? AND entity_id = ? ORDER BY sequence", (entity_type, entity_id))

    def report(self, *, batch_id: str | None = None) -> dict[str, Any]:
        recs = self.reconciliations(batch_id=batch_id)
        counts: dict[str, int] = {}
        for rec in recs:
            outcome = rec.get("outcome") or rec.get("state")
            counts[outcome] = counts.get(outcome, 0) + 1
        watermark = self.database.connection.execute("SELECT COUNT(*) AS count, MAX(timestamp) AS timestamp FROM audit_events").fetchone()
        return {"batch_id": batch_id, "reconciliation_count": len(recs), "outcomes": counts,
                "discrepancy_count": len(self.discrepancies(batch_id=batch_id)),
                "source_watermark": {"event_count": watermark["count"], "timestamp": watermark["timestamp"]}}

    def health(self) -> dict[str, Any]:
        try:
            self.database.connection.execute("SELECT 1").fetchone()
            return {"status": "ok", "application": "ok", "database": "ok"}
        except Exception:
            return {"status": "degraded", "application": "ok", "database": "unavailable"}

    def export(self, *, batch_id: str | None = None) -> dict[str, Any]:
        # Export is intentionally a projection and excludes raw payloads/secrets.
        return _redact_export({"report": self.report(batch_id=batch_id), "reconciliations": self.reconciliations(batch_id=batch_id),
                "discrepancies": self.discrepancies(batch_id=batch_id)})
