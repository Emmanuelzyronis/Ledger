"""Real-service pipeline driver used by every product-proof scenario.

This module contains no product semantics of its own. It only sequences the
existing Layer 1-14 services exactly as the Layer 13 benchmark runner does:
ingest -> validate -> normalize -> identify -> candidate generation -> match,
plus the raw-only invalid reconciliation route. Every scenario runs against a
real LedgerDatabase (memory or file) with fixed fixture payloads.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from ledger.candidates import CandidateGenerationService
from ledger.domain import ReconciliationOutcome
from ledger.identity import IdentityService
from ledger.ingestion import RawIngestion
from ledger.matching import MatchingService
from ledger.normalization import NormalizationService
from ledger.persistence import LedgerDatabase
from ledger.reconciliation import ReconciliationService
from ledger.validation import ValidationService

from . import dataset


def register_sources(ingestion: RawIngestion) -> None:
    ingestion.register_source("source-a", "Source A", ["source_a.v1"])
    ingestion.register_source("source-b", "Source B", ["source_b.v1"])


def seed_records(
    database: LedgerDatabase,
    source: str,
    schema_version: str,
    records: Mapping[str, Mapping[str, Any]],
    *,
    batch_id: str,
    external_batch_id: str,
    idempotency_prefix: str,
    received_at: datetime | None = None,
    accepted_at: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Ingest every payload once and return (batch_id, record_id -> IngestionResult)."""
    timestamp = received_at or dataset.now()
    ingestion = RawIngestion(database)
    batch = ingestion.create_batch(source, external_batch_id, schema_version,
                                   batch_id=batch_id, received_at=timestamp)
    results: dict[str, Any] = {}
    for record_id in sorted(records):
        payload = records[record_id]
        result = ingestion.ingest(batch.batch_id, payload,
                                  idempotency_key=f"{idempotency_prefix}:{record_id}",
                                  accepted_at=accepted_at or timestamp)
        results[record_id] = result
    return batch.batch_id, results


def validate_batches(database: LedgerDatabase, batch_ids: Sequence[str]) -> list[Any]:
    validation = ValidationService(database)
    results: list[Any] = []
    for batch_id in batch_ids:
        results.extend(validation.validate_batch(batch_id))
    return results


def normalize_raw_ids(database: LedgerDatabase, raw_ids: Iterable[str]) -> list[Any]:
    normalization = NormalizationService(database)
    return [item for raw_id in raw_ids if (item := normalization.normalize_record(raw_id, created_at=dataset.now())) is not None]


def verify_identities(database: LedgerDatabase) -> list[Any]:
    identity = IdentityService(database)
    return [identity.identify(transaction) for transaction in database.canonical_transactions.list_all()]


def generate_candidates(database: LedgerDatabase) -> list[Any]:
    return CandidateGenerationService(database).generate_all()


def evaluate_matching(database: LedgerDatabase, *, evaluated_at: datetime | None = None) -> list[Any]:
    return MatchingService(database).evaluate(evaluated_at=evaluated_at or dataset.now())


def reconcile_invalid_records(database: LedgerDatabase, batch_ids: Sequence[str]) -> list[Any]:
    """Create raw-only INVALID reconciliations for validation-invalid records."""
    reconciliation = ReconciliationService(database)
    created: list[Any] = []
    for batch_id in batch_ids:
        for raw in database.raw_records.list_for_batch(batch_id):
            if raw.invalid_reason is not None:
                continue
            result = database.validation_results.get_for_raw(raw.raw_record_id, dataset.VALIDATION_VERSION)
            if result is not None and result.status == "INVALID":
                created.append(reconciliation.reconcile_invalid(
                    raw.raw_record_id, batch_id=raw.batch_id,
                    evidence={"validation": "INVALID", "validation_version": result.validation_version}))
    return created


def run_standard_pipeline(
    database: LedgerDatabase,
    batch_ids: Sequence[str],
    *,
    reconcile_invalid: bool = False,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Run every pipeline stage over the given batches using real services.

    Returns a snapshot of identities, candidates, and decisions. Replaying the
    same call over the same database must return the same authoritative rows
    because each stage is idempotent.
    """
    validate_batches(database, batch_ids)
    raw_ids: list[str] = []
    for batch_id in batch_ids:
        raw_ids.extend(row.raw_record_id for row in database.raw_records.list_for_batch(batch_id))
    canonical = normalize_raw_ids(database, raw_ids)
    identities = verify_identities(database)
    candidates = generate_candidates(database)
    decisions = evaluate_matching(database, evaluated_at=evaluated_at)
    invalid_reconciliations = reconcile_invalid_records(database, batch_ids) if reconcile_invalid else []
    return {
        "canonical": canonical,
        "identities": identities,
        "candidates": candidates,
        "decisions": decisions,
        "invalid_reconciliations": invalid_reconciliations,
    }


def reconciliation_rows(database: LedgerDatabase) -> list[dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in database.connection.execute(
        "SELECT * FROM reconciliations ORDER BY reconciliation_id").fetchall()]


def initial_decision_rows(database: LedgerDatabase) -> list[dict[str, Any]]:
    """Initial terminal decision rows: outcome-bearing rows that are not superseded."""
    return [row for row in reconciliation_rows(database)
            if row["outcome"] is not None and row["supersedes_reconciliation_id"] is None]


def record_outcomes(database: LedgerDatabase) -> dict[str, dict[str, Any]]:
    """Map every raw record to its initial reconciliation outcome.

    A decision row names the canonical transaction(s) it decides; the outcome
    applies to each named record. Pair rows therefore report one outcome for
    both source records. INVALID rows are raw-only lineage.
    """
    raw_by_canonical: dict[str, Any] = {
        transaction.canonical_id: database.raw_records.get(transaction.raw_record_id)
        for transaction in database.canonical_transactions.list_all()
    }
    outcomes: dict[str, dict[str, Any]] = {}
    for row in initial_decision_rows(database):
        names: list[str] = []
        for column in ("source_a_record_id", "source_b_record_id"):
            canonical_id = row[column]
            raw = raw_by_canonical.get(canonical_id)
            if raw is not None:
                names.append(raw.source_record_id)
        raw = database.raw_records.get(row["raw_record_id"]) if row["raw_record_id"] else None
        if raw is not None and raw.source_record_id not in names:
            names.append(raw.source_record_id)
        for name in names:
            outcomes[name] = {
                "outcome": row["outcome"],
                "state": row["state"],
                "reconciliation_id": row["reconciliation_id"],
                "reconciliation_version": row["reconciliation_version"],
                "counterpart": _counterpart_for_record(database, row, name),
            }
    return outcomes


def _counterpart_for_record(database: LedgerDatabase, row: dict[str, Any], record_id: str) -> str | None:
    """Return the source-native id of the other side of a pair decision row."""
    raw_by_canonical: dict[str, Any] = {
        transaction.canonical_id: database.raw_records.get(transaction.raw_record_id)
        for transaction in database.canonical_transactions.list_all()
    }
    result: list[str] = []
    for column in ("source_a_record_id", "source_b_record_id"):
        canonical_id = row[column]
        raw = raw_by_canonical.get(canonical_id)
        if raw is not None and raw.source_record_id != record_id:
            result.append(raw.source_record_id)
    return result[0] if len(result) == 1 else None


def outcome_counts(database: LedgerDatabase, *, include_superseded: bool = True) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = reconciliation_rows(database) if include_superseded else initial_decision_rows(database)
    for row in rows:
        outcome = row["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def row_count(database: LedgerDatabase, table: str) -> int:
    return int(database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
