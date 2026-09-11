"""Versioned schema migrations and migration history (Epic 5 / EMM-81).

The Layer 3 schema is the *baseline*. It is created idempotently by
``LedgerDatabase._create_schema`` and recorded here as migration ``0001`` so the
history is explicit and every later schema change is a numbered, ordered,
transactional migration.

Rules:

- Migrations are ordered by version and applied exactly once per database.
- Each migration runs in one transaction; a failure leaves the schema and the
  history unchanged (no partially applied version).
- ``apply`` is idempotent: running it against an up-to-date database applies
  nothing and returns an empty list.
- A database created before this module existed is *adopted*: the baseline is
  recorded against the schema that is already present rather than re-executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

BASELINE_VERSION = "0001"
BASELINE_NAME = "initial_schema"
HISTORY_TABLE = "schema_migrations"


class DatabaseLike(Protocol):
    """The slice of ``LedgerDatabase`` a migration runner needs."""

    connection: Any

    def transaction(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    statements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MigrationRecord:
    version: str
    name: str
    applied_at: str
    baseline: bool


# --------------------------------------------------------------------------
# The migration set. ``0001`` is the baseline created by _create_schema; every
# entry after it must be additive and idempotent (IF NOT EXISTS) so replaying a
# migration cannot corrupt an adopted database.
# --------------------------------------------------------------------------
MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version="0002",
        name="operational_lookup_indexes",
        statements=(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_entity "
            "ON audit_events(entity_type, entity_id, sequence)",
            "CREATE INDEX IF NOT EXISTS idx_discrepancies_reconciliation "
            "ON discrepancies(reconciliation_id)",
            "CREATE INDEX IF NOT EXISTS idx_reconciliations_batch "
            "ON reconciliations(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_raw_records_batch "
            "ON raw_records(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_validation_results_batch "
            "ON validation_results(batch_id)",
        ),
    ),
)


class MigrationError(RuntimeError):
    """A migration could not be applied; the database is left unchanged."""


class MigrationRunner:
    def __init__(self, database: DatabaseLike) -> None:
        self.database = database

    # -- history ---------------------------------------------------------
    def ensure_history(self) -> None:
        self.database.connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                baseline INTEGER NOT NULL CHECK (baseline IN (0, 1))
            )
            """
        )

    def history(self) -> list[MigrationRecord]:
        self.ensure_history()
        rows = self.database.connection.execute(
            f"SELECT version, name, applied_at, baseline FROM {HISTORY_TABLE} ORDER BY version"  # nosec B608 - HISTORY_TABLE is a module constant
        ).fetchall()
        return [MigrationRecord(row[0], row[1], row[2], bool(row[3])) for row in rows]

    def applied_versions(self) -> set[str]:
        return {record.version for record in self.history()}

    def pending(self) -> list[Migration]:
        applied = self.applied_versions()
        return [migration for migration in MIGRATIONS if migration.version not in applied]

    # -- application -----------------------------------------------------
    def apply(self) -> list[Migration]:
        """Apply every pending migration; return the ones applied by this call."""
        self.ensure_history()
        applied = self.applied_versions()
        if BASELINE_VERSION not in applied:
            # The baseline DDL already ran (or the database predates migrations);
            # record it rather than re-executing it.
            with self.database.transaction():
                self._record(BASELINE_VERSION, BASELINE_NAME, baseline=True)
            applied.add(BASELINE_VERSION)
        newly_applied: list[Migration] = []
        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            try:
                with self.database.transaction():
                    for statement in migration.statements:
                        self.database.connection.execute(statement)
                    self._record(migration.version, migration.name, baseline=False)
            except Exception as exc:  # pragma: no cover - exercised by failure tests
                raise MigrationError(
                    f"migration {migration.version} ({migration.name}) failed: {exc}"
                ) from exc
            newly_applied.append(migration)
        return newly_applied

    def _record(self, version: str, name: str, *, baseline: bool) -> None:
        self.database.connection.execute(
            f"INSERT INTO {HISTORY_TABLE}(version, name, applied_at, baseline) VALUES (?, ?, ?, ?)",  # nosec B608 - HISTORY_TABLE is a module constant; values are bound
            (version, name, datetime.now(timezone.utc).isoformat(), 1 if baseline else 0),
        )

    # -- reporting -------------------------------------------------------
    def describe(self) -> list[dict[str, Any]]:
        applied = {record.version: record for record in self.history()}
        rows: list[dict[str, Any]] = []
        entries: list[tuple[str, str, bool]] = [(BASELINE_VERSION, BASELINE_NAME, True)]
        entries.extend((migration.version, migration.name, False) for migration in MIGRATIONS)
        for version, name, baseline in entries:
            record = applied.get(version)
            rows.append({
                "version": version,
                "name": name,
                "baseline": baseline,
                "state": "applied" if record else "pending",
                "applied_at": record.applied_at if record else None,
            })
        return rows
