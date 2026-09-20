"""Small framework-independent HTTP/application boundary for LEDGER Layer 12."""

from __future__ import annotations

import uuid
from dataclasses import is_dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

from .domain import ResolutionType
from .ingestion import RawIngestion
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase
from .reporting import ReportingService
from .resolution import ResolutionService


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """HTTP header lookup is case-insensitive (RFC 7230 field-name rules)."""
    target = name.casefold()
    for key, value in headers.items():
        if key.casefold() == target:
            return value
    return None


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


class LedgerAPI:
    def __init__(self, database: LedgerDatabase, *, token_verifier: Callable[[str], Mapping[str, Any] | None] | None = None,
                 telemetry: TelemetrySink | None = None, ingestion: RawIngestion | None = None,
                 resolution: ResolutionService | None = None) -> None:
        self.database = database
        self.token_verifier = token_verifier or (lambda token: None)
        self.telemetry = telemetry
        self.ingestion = ingestion or RawIngestion(database, telemetry=telemetry)
        self.resolution = resolution or ResolutionService(database, telemetry=telemetry)
        self.reporting = ReportingService(database)

    def handle(self, method: str, path: str, body: Any = None, headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
        headers = headers or {}
        parsed = urlsplit(path)
        path = parsed.path
        if body is None and parsed.query:
            body = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        correlation_id = _header(headers, "X-Correlation-ID") or str(uuid.uuid4())
        try:
            principal = self._authenticate(headers)
            result = self._dispatch(method.upper(), path.strip("/"), body, principal)
            self._emit(correlation_id, method, path, 200)
            return 200, {"data": self._convert(result), "correlation_id": correlation_id}
        except APIError as exc:
            self._emit(correlation_id, method, path, exc.status)
            return exc.status, {"error": {"code": exc.code, "message": exc.message}, "correlation_id": correlation_id}
        except (ValueError, KeyError, TypeError) as exc:
            self._emit(correlation_id, method, path, 400)
            return 400, {"error": {"code": "invalid_request", "message": str(exc)}, "correlation_id": correlation_id}

    def _authenticate(self, headers: Mapping[str, str]) -> Mapping[str, Any]:
        value = _header(headers, "Authorization") or ""
        if not value.startswith("Bearer "):
            raise APIError(401, "authentication_required", "bearer authentication is required")
        principal = self.token_verifier(value[7:].strip())
        if not principal:
            raise APIError(401, "invalid_token", "authentication failed")
        return principal

    def _dispatch(self, method: str, path: str, body: Any, principal: Mapping[str, Any]) -> Any:
        # Percent-decode each segment after splitting so an encoded "/" can never
        # change the structure of the route (RFC 3986 path segment semantics).
        parts = [unquote(segment) for segment in path.split("/")] if path else []
        if method == "GET" and parts == ["health"]:
            return self.reporting.health()
        if method == "GET" and parts == ["ready"]:
            health = self.reporting.health()
            if health["database"] != "ok": raise APIError(503, "not_ready", "database unavailable")
            return health
        if method == "GET" and parts == ["reports"]:
            batch_id = (body or {}).get("batch_id") if isinstance(body, dict) else None
            self._authorize_batch_filter(principal, batch_id)
            return self.reporting.report(batch_id=batch_id)
        if method == "GET" and parts == ["batches"]:
            source_id = (body or {}).get("source_id") if isinstance(body, dict) else None
            if source_id is not None:
                self._scope(principal, source_id)
            return self._filter_rows(principal, self.reporting.batches(source_id=source_id))
        if method == "GET" and parts == ["export"]:
            batch_id = (body or {}).get("batch_id") if isinstance(body, dict) else None
            self._authorize_batch_filter(principal, batch_id)
            return self.reporting.export(batch_id=batch_id)
        if method == "POST" and parts == ["sources"]:
            data = self._object(body, ("source_id", "name", "schema_versions"))
            return self.ingestion.register_source(data["source_id"], data["name"], data["schema_versions"], active=data.get("active", True))
        if method == "POST" and parts == ["batches"]:
            data = self._object(body, ("source_id", "external_batch_id", "schema_version"))
            self._scope(principal, data["source_id"])
            return self.ingestion.create_batch(**data)
        if method == "POST" and len(parts) == 3 and parts[0] == "batches" and parts[2] == "records":
            batch = self.database.batches.get(parts[1])
            if batch is None: raise APIError(404, "not_found", "batch does not exist")
            self._scope(principal, batch.source_id)
            if not isinstance(body, dict) or "payload" not in body:
                raise APIError(400, "missing_field", "missing required field: payload")
            return self.ingestion.ingest(parts[1], body["payload"], idempotency_key=body.get("idempotency_key"))
        if method == "GET" and len(parts) == 2 and parts[0] == "batches":
            batch = self.database.batches.get(parts[1]);
            if batch is None: raise APIError(404, "not_found", "batch does not exist")
            self._scope(principal, batch.source_id)
            return self.reporting.batch_status(parts[1])
        if method == "GET" and parts == ["reconciliations"]:
            batch_id = (body or {}).get("batch_id") if isinstance(body, dict) else None
            self._authorize_batch_filter(principal, batch_id)
            rows = self.reporting.reconciliations(batch_id=batch_id)
            return self._filter_rows(principal, rows)
        if method == "GET" and len(parts) == 2 and parts[0] == "reconciliations":
            row = self.database.reconciliations.get(parts[1])
            if row is None: raise APIError(404, "not_found", "reconciliation does not exist")
            batch = self.database.batches.get(row.batch_id)
            if batch: self._scope(principal, batch.source_id)
            return self.reporting._rows("reconciliations", " WHERE reconciliation_id = ?", (parts[1],))[0]
        if method == "GET" and parts == ["discrepancies"]:
            batch_id = (body or {}).get("batch_id") if isinstance(body, dict) else None
            self._authorize_batch_filter(principal, batch_id)
            return self._filter_rows(principal, self.reporting.discrepancies(batch_id=batch_id))
        if method == "GET" and len(parts) == 2 and parts[0] == "discrepancies":
            row = self.database.discrepancies.get(parts[1])
            if row is None: raise APIError(404, "not_found", "discrepancy does not exist")
            rec = self.database.reconciliations.get(row.reconciliation_id)
            if rec:
                batch = self.database.batches.get(rec.batch_id)
                if batch: self._scope(principal, batch.source_id)
            return self.reporting._rows("discrepancies", " WHERE discrepancy_id = ?", (parts[1],))[0]
        if method == "GET" and len(parts) == 3 and parts[0] == "audit":
            self._scope_audit(principal, parts[1], parts[2]); return self.reporting.audit(parts[1], parts[2])
        if method == "POST" and len(parts) == 3 and parts[0] == "discrepancies" and parts[2] == "resolve":
            self._require_role(principal, "reconciliation_operator")
            data = self._object(body, ("resolution_type", "reason"))
            return self.resolution.resolve(parts[1], ResolutionType(data["resolution_type"]), actor="reconciliation_operator", reason=data["reason"], evidence=data.get("evidence"), rule_version=data.get("rule_version"))
        if method == "POST" and parts == ["dev", "seed"]:
            import os
            if os.environ.get("LEDGER_ALLOW_SEED") != "true":
                raise APIError(404, "not_found", "endpoint does not exist")
            self._require_role(principal, "reconciliation_operator")
            return self._run_seed()
        raise APIError(404, "not_found", "endpoint does not exist")

    @staticmethod
    def _object(body: Any, required: tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(body, dict): raise APIError(400, "invalid_json", "request body must be a JSON object")
        missing = [key for key in required if key not in body]
        if missing: raise APIError(400, "missing_field", f"missing required field: {missing[0]}")
        return body

    @staticmethod
    def _require_role(principal: Mapping[str, Any], role: str) -> None:
        roles = principal.get("roles", ())
        if role not in roles and principal.get("role") != role: raise APIError(403, "forbidden", "insufficient role")

    @staticmethod
    def _scope(principal: Mapping[str, Any], source_id: str) -> None:
        allowed = principal.get("source_ids")
        if allowed is not None and source_id not in allowed: raise APIError(403, "forbidden", "source is outside caller scope")

    def _scope_audit(self, principal: Mapping[str, Any], entity_type: str, entity_id: str) -> None:
        if entity_type == "batch":
            batch = self.database.batches.get(entity_id)
            if batch: self._scope(principal, batch.source_id)
        elif entity_type == "reconciliation":
            rec = self.database.reconciliations.get(entity_id)
            if rec: self._authorize_batch_filter(principal, rec.batch_id)
        elif entity_type == "discrepancy":
            row = self.database.discrepancies.get(entity_id)
            if row: self._authorize_discrepancy_scope(principal, row.reconciliation_id)
        elif entity_type == "resolution":
            row = self.database.resolutions.get(entity_id)
            if row: self._authorize_discrepancy_scope(principal, row.reconciliation_id)
        elif entity_type == "record":
            raw = self.database.raw_records.get(entity_id)
            if raw: self._authorize_batch_filter(principal, raw.batch_id)

    def _authorize_discrepancy_scope(self, principal: Mapping[str, Any], reconciliation_id: str) -> None:
        """Scope a discrepancy or resolution to the source of its reconciliation's batch."""
        reconciliation = self.database.reconciliations.get(reconciliation_id)
        if reconciliation:
            self._authorize_batch_filter(principal, reconciliation.batch_id)

    def _authorize_batch_filter(self, principal: Mapping[str, Any], batch_id: str | None) -> None:
        if batch_id:
            batch = self.database.batches.get(batch_id)
            if batch is None: raise APIError(404, "not_found", "batch does not exist")
            self._scope(principal, batch.source_id)

    def _filter_rows(self, principal: Mapping[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = principal.get("source_ids")
        if allowed is None: return rows
        result = []
        for row in rows:
            batch_id = row.get("batch_id")
            if batch_id is None:
                # Discrepancy projections carry a reconciliation id, not a batch
                # id; resolve the batch through that link so source scoping applies.
                reconciliation_id = row.get("reconciliation_id")
                reconciliation = self.database.reconciliations.get(reconciliation_id) if reconciliation_id else None
                batch_id = reconciliation.batch_id if reconciliation else None
            batch = self.database.batches.get(batch_id) if batch_id else None
            if batch is not None and batch.source_id in allowed: result.append(row)
        return result

    def _emit(self, correlation_id: str, method: str, path: str, status: int) -> None:
        if self.telemetry: self.telemetry.emit(TelemetryEvent("ledger.api.request", CorrelationContext(), {"correlation_id": correlation_id, "method": method, "path": path, "status": status}))

    @staticmethod
    def _convert(value: Any) -> Any:
        if is_dataclass(value):
            return {field: LedgerAPI._convert(getattr(value, field)) for field in getattr(value, "__dataclass_fields__", {})}
        if isinstance(value, Mapping): return {str(k): LedgerAPI._convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)): return [LedgerAPI._convert(v) for v in value]
        if hasattr(value, "value"): return value.value
        if hasattr(value, "isoformat"): return value.isoformat()
        return value


    def _run_seed(self) -> dict[str, Any]:
        from datetime import datetime, timezone
        from .pipeline import process_batches, select_batches

        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

        PORTFOLIO_A = {
            "A001": {"record_id": "A001", "occurred_at": "2026-09-01", "amount": "100.00", "currency": "USD", "direction": "CREDIT", "transaction_reference": "TX-1001"},
            "A002": {"record_id": "A002", "occurred_at": "2026-09-02", "amount": "250.00", "currency": "USD", "direction": "CREDIT", "transaction_reference": "TX-1002"},
            "A003": {"record_id": "A003", "occurred_at": "2026-09-03", "amount": "500.00", "currency": "USD", "direction": "CREDIT"},
            "A004": {"record_id": "A004", "occurred_at": "2026-09-03", "amount": "100.00", "currency": "USD", "direction": "CREDIT"},
            "A005": {"record_id": "A005", "occurred_at": "2026-09-03", "amount": "100.00x", "currency": "USD", "direction": "CREDIT"},
            "A006": {"record_id": "A006", "occurred_at": "2026-09-04", "amount": "600.00", "currency": "USD", "direction": "CREDIT", "transaction_reference": "TX-1006"},
            "A007": {"record_id": "A007", "occurred_at": "2026-09-06", "amount": "800.00", "currency": "USD", "direction": "CREDIT", "transaction_reference": "TX-1007"},
            "D-A1": {"record_id": "D-A1", "occurred_at": "2026-09-05", "amount": "300.00", "currency": "USD", "direction": "CREDIT"},
            "D-A2": {"record_id": "D-A2", "occurred_at": "2026-09-05", "amount": "301.00", "currency": "USD", "direction": "CREDIT", "transaction_reference": "DUP-9"},
        }
        PORTFOLIO_B = {
            "B991": {"id": "B991", "posted": "2026-09-01", "value": "100.00", "ccy": "USD", "side": "DEBIT", "reference": "TX-1001"},
            "B992": {"id": "B992", "posted": "2026-09-02", "value": "250.00", "ccy": "USD", "side": "DEBIT", "reference": "TX-1002"},
            "B993": {"id": "B993", "posted": "2026-09-03", "value": "750.00", "ccy": "USD", "side": "DEBIT"},
            "B994": {"id": "B994", "posted": "2026-09-03", "value": "100.00", "ccy": "USD", "side": "DEBIT"},
            "B995": {"id": "B995", "posted": "2026-09-03", "value": "100.00", "ccy": "USD", "side": "DEBIT"},
            "B996": {"id": "B996", "posted": "2026-09-04", "value": "999.00", "ccy": "USD", "side": "DEBIT", "reference": "TX-1006"},
            "B997": {"id": "B997", "posted": "2026-09-06", "value": "800.00", "ccy": "USD", "side": "CREDIT", "reference": "TX-1007"},
            "D-B1": {"id": "D-B1", "posted": "2026-09-05", "value": "300.00", "ccy": "USD", "side": "DEBIT", "reference": "DUP-9"},
        }

        self.ingestion.register_source("source-a", "Source A", ["source_a.v1"])
        self.ingestion.register_source("source-b", "Source B", ["source_b.v1"])

        batch_a = self.ingestion.create_batch("source-a", "seed-ext-a", "source_a.v1", batch_id="seed-batch-a", received_at=now)
        for key in sorted(PORTFOLIO_A):
            self.ingestion.ingest(batch_a.batch_id, PORTFOLIO_A[key], idempotency_key=f"seed-a:{key}", accepted_at=now)

        batch_b = self.ingestion.create_batch("source-b", "seed-ext-b", "source_b.v1", batch_id="seed-batch-b", received_at=now)
        for key in sorted(PORTFOLIO_B):
            self.ingestion.ingest(batch_b.batch_id, PORTFOLIO_B[key], idempotency_key=f"seed-b:{key}", accepted_at=now)

        batch_ids = select_batches(self.database, batch_ids=[batch_a.batch_id, batch_b.batch_id])
        runs = process_batches(self.database, batch_ids, evaluated_at=now)

        report = self.reporting.report()
        return {
            "seeded": True,
            "runs": [r.as_dict() for r in runs],
            "reconciliation_count": report.get("current_reconciliation_count", 0),
            "outcomes": report.get("current_outcomes", {}),
        }


def create_app(database: LedgerDatabase, **kwargs: Any) -> LedgerAPI:
    return LedgerAPI(database, **kwargs)
