"""Retention and least-privilege controls for authoritative state (EMM-81).

Retention is fail-closed. An operational job must name a table that is
explicitly classified as prunable, and in v1.0 no table is: LEDGER retains raw
evidence, canonical versions, reconciliation versions, discrepancies,
resolutions, and audit events indefinitely. Pruning is not implemented because
match evidence references candidate ids, so deleting candidates would make
retained evidence unreadable.

Export files, logs, and telemetry are retained by the deployment, not by this
module; they are derived and never authoritative.
"""

from __future__ import annotations

import sqlite3
from urllib.parse import quote

AUTHORITATIVE_TABLES = frozenset({
    "sources",
    "batches",
    "processing_attempts",
    "raw_records",
    "raw_record_batches",
    "validation_results",
    "ingestion_submissions",
    "canonical_transactions",
    "match_candidates",
    "reconciliations",
    "discrepancies",
    "resolutions",
    "audit_events",
    "schema_migrations",
})

# Derived, rebuildable state that a future approved policy may prune.
PRUNABLE_TABLES: frozenset[str] = frozenset()


class RetentionError(RuntimeError):
    """A retention request would delete state that must be preserved."""


def assert_prunable(table: str) -> None:
    if table in AUTHORITATIVE_TABLES:
        raise RetentionError(
            f"{table!r} holds authoritative or evidence-referenced state and is never pruned"
        )
    if table not in PRUNABLE_TABLES:
        raise RetentionError(f"{table!r} is not classified as prunable")


def describe() -> dict[str, list[str]]:
    return {"retained": sorted(AUTHORITATIVE_TABLES), "prunable": sorted(PRUNABLE_TABLES)}


def open_readonly(path: str) -> sqlite3.Connection:
    """Open an existing database read-only, for verification and reporting.

    ``mode=ro`` fails closed if the file is missing and ``query_only`` rejects
    any write the caller attempts. Least privilege for operators is: the service
    account owns the writer; verification and reporting use this.
    """
    connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection
