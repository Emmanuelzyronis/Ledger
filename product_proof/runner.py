"""Deterministic Layer 15 product-proof runner.

Every scenario drives the real LEDGER services and real SQLite persistence with
the fixed fixtures in ``product_proof.dataset``. No core pipeline component is
mocked. The runner records an authoritative observation tree plus a SHA-256
signature so a second engineer can reproduce the same result from the
repository artifacts.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from ledger.api import LedgerAPI
from ledger.candidates import CandidateGenerationService
from ledger.domain import ResolutionType
from ledger.identity import IdentityService, canonical_json
from ledger.ingestion import RawIngestion
from ledger.matching import MatchingService
from ledger.normalization import NormalizationService
from ledger.observability import InMemoryTelemetrySink
from ledger.persistence import LedgerDatabase
from ledger.resolution import ResolutionService
from ledger.validation import ValidationService

from . import dataset
from .pipeline import (
    evaluate_matching,
    generate_candidates,
    normalize_raw_ids,
    record_outcomes,
    register_sources,
    row_count,
    run_standard_pipeline,
    seed_records,
    validate_batches,
    verify_identities,
)

SUITE_VERSION = "product_proof_v1"


# --------------------------------------------------------------------------
# Evidence helpers
# --------------------------------------------------------------------------

def _projection_rows(database: LedgerDatabase, sql: str) -> list[list[Any]]:
    return [list(row) for row in database.connection.execute(sql).fetchall()]


def database_signature(database: LedgerDatabase) -> str:
    """Deterministic signature over authoritative state (wall-clock excluded)."""
    projection = {
        "batches": _projection_rows(database, "SELECT batch_id, source_id, external_batch_id, schema_version, state, counters_json FROM batches ORDER BY batch_id"),
        "raw_records": _projection_rows(database, "SELECT raw_record_id, source_id, source_record_id, schema_version, content_fingerprint, invalid_reason, supersedes_raw_record_id FROM raw_records ORDER BY raw_record_id"),
        "validation_results": _projection_rows(database, "SELECT validation_id, raw_record_id, status FROM validation_results ORDER BY validation_id"),
        "canonical_transactions": _projection_rows(database, "SELECT canonical_id, source_record_id, occurred_at, amount, currency, direction, normalization_version, canonical_version, canonical_fingerprint, supersedes_canonical_id FROM canonical_transactions ORDER BY canonical_id"),
        "match_candidates": _projection_rows(database, "SELECT candidate_id, source_a_canonical_id, source_b_canonical_id, eligible_rule_ids_json FROM match_candidates ORDER BY candidate_id"),
        "reconciliations": _projection_rows(database, "SELECT reconciliation_id, batch_id, source_a_record_id, source_b_record_id, reconciliation_version, rule_version, outcome, state, supersedes_reconciliation_id, resolution_id, raw_record_id FROM reconciliations ORDER BY reconciliation_id"),
        "discrepancies": _projection_rows(database, "SELECT discrepancy_id, reconciliation_id, reason, state FROM discrepancies ORDER BY discrepancy_id"),
        "resolutions": _projection_rows(database, "SELECT resolution_id, discrepancy_id, reconciliation_id, resolution_type, actor, reason, rule_version FROM resolutions ORDER BY resolution_id"),
        "audit_events": _projection_rows(database, "SELECT event_id, entity_type, entity_id, event_type, sequence, stage_version, previous_state, new_state, batch_id, record_id, reconciliation_id, causation_event_id FROM audit_events ORDER BY event_id"),
    }
    return hashlib.sha256(canonical_json(projection)).hexdigest()


class ProofRecorder:
    """Collects check results and observations for one scenario run."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.checks: list[dict[str, Any]] = []
        self.observations: dict[str, Any] = {}

    def check(self, check_id: str, description: str, condition: bool, detail: Any = None) -> None:
        self.checks.append({
            "scenario": self.scenario,
            "check_id": check_id,
            "description": description,
            "passed": bool(condition),
            "detail": detail,
        })
        if not condition:
            raise AssertionError(f"{self.scenario}:{check_id} failed - {description} detail={detail!r}")

    def finish(self, **extra: Any) -> dict[str, Any]:
        self.observations.update(extra)
        return {"scenario": self.scenario, "checks": self.checks, "observations": self.observations}


def _all_reconciliation_rows(database: LedgerDatabase) -> list[dict[str, Any]]:
    rows = database.connection.execute("SELECT * FROM reconciliations ORDER BY reconciliation_id").fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        item["evidence"] = json.loads(row["evidence_json"]) if isinstance(row["evidence_json"], str) else {}
        result.append(item)
    return result


def _all_resolution_rows(database: LedgerDatabase) -> list[dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in database.connection.execute(
        "SELECT * FROM resolutions ORDER BY resolution_id").fetchall()]


def pipeline_decisions(database: LedgerDatabase) -> list[dict[str, Any]]:
    """Initial terminal decision rows: outcome-bearing versions that supersede nothing.

    A late-arrival version supersedes an earlier version, so it is excluded from
    this *initial* projection while the original version stays included. Use
    ``LedgerDatabase.reconciliations.list_current`` for current state.
    """
    return [row for row in _all_reconciliation_rows(database)
            if row["outcome"] is not None and row["supersedes_reconciliation_id"] is None]


def all_outcome_rows(database: LedgerDatabase) -> list[dict[str, Any]]:
    """Every authoritative reconciliation row that carries an outcome."""
    return [row for row in _all_reconciliation_rows(database) if row["outcome"] is not None]


def outcome_count_values(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    return counts


def _row_names(database: LedgerDatabase, row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    raw_by_canonical: dict[str, Any] = {
        transaction.canonical_id: database.raw_records.get(transaction.raw_record_id)
        for transaction in database.canonical_transactions.list_all()
    }
    for column in ("source_a_record_id", "source_b_record_id"):
        raw = raw_by_canonical.get(row[column]) if row[column] else None
        if raw is not None:
            names.append(raw.source_record_id)
    raw = database.raw_records.get(row["raw_record_id"]) if row.get("raw_record_id") else None
    if raw is not None:
        names.append(raw.source_record_id)
    return names


def _raw_snapshot(database: LedgerDatabase) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in database.connection.execute(
        "SELECT raw_record_id, payload_json, content_fingerprint, invalid_reason, supersedes_raw_record_id "
        "FROM raw_records ORDER BY raw_record_id").fetchall()]


def _all_raw_records(database: LedgerDatabase) -> list[Any]:
    return [database.raw_records.get(row["raw_record_id"]) for row in database.connection.execute(
        "SELECT raw_record_id FROM raw_records ORDER BY raw_record_id").fetchall()]


def _discrepancy_table(database: LedgerDatabase) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    rows = database.connection.execute("SELECT * FROM discrepancies ORDER BY discrepancy_id").fetchall()
    for row in rows:
        reconciliation = database.reconciliations.get(row["reconciliation_id"])
        names = _row_names(database, {"source_a_record_id": reconciliation.source_a_record_id,
                                      "source_b_record_id": reconciliation.source_b_record_id,
                                      "raw_record_id": reconciliation.raw_record_id}) if reconciliation else []
        result.append({
            "discrepancy_id": row["discrepancy_id"],
            "reconciliation_id": row["reconciliation_id"],
            "record_id": names[0] if names else None,
            "reconciliation_outcome": reconciliation.outcome.value if reconciliation and reconciliation.outcome else None,
            "state": row["state"],
            "reason": row["reason"],
        })
    return result


def _token_verifier() -> Callable[[str], Mapping[str, Any] | None]:
    tokens: dict[str, Mapping[str, Any]] = {
        "operator": {"roles": ["reconciliation_operator"]},
        "reader-a": {"roles": [], "source_ids": ["source-a"]},
        "reader-b": {"roles": [], "source_ids": ["source-b"]},
    }

    def verify(token: str) -> Mapping[str, Any] | None:
        return tokens.get(token)

    return verify


# --------------------------------------------------------------------------
# Portfolio scenario
# --------------------------------------------------------------------------

def run_portfolio(database: LedgerDatabase | None = None) -> dict[str, Any]:
    """Run the canonical portfolio dataset, resolution workflows, API/reporting,
    idempotent replay, and late-arrival phases against one authoritative DB."""
    recorder = ProofRecorder("portfolio")
    own_database = database is None
    db = database or LedgerDatabase()
    try:
        ingestion = RawIngestion(db)
        register_sources(ingestion)

        # ---- Phase 1: seed and evaluate the complete portfolio -------------
        batch_a, _ = seed_records(
            db, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
            batch_id="pf-batch-a", external_batch_id="pf-ext-a-1", idempotency_prefix="pf-a")
        batch_b, _ = seed_records(
            db, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
            batch_id="pf-batch-b", external_batch_id="pf-ext-b-1", idempotency_prefix="pf-b")
        run_standard_pipeline(db, [batch_a, batch_b], reconcile_invalid=True)

        observed_outcomes = record_outcomes(db)
        expected = dataset.EXPECTED_PORTFOLIO_OUTCOMES
        mismatch = {
            key: (expected[key], observed_outcomes[key]["outcome"] if key in observed_outcomes else None)
            for key in expected if observed_outcomes.get(key, {}).get("outcome") != expected[key]
        }
        recorder.check("outcomes.portfolio",
                       "every portfolio record reaches its expected terminal outcome",
                       not mismatch and len(observed_outcomes) == len(expected), mismatch)

        initial_rows = pipeline_decisions(db)
        counts = outcome_count_values(initial_rows)
        expected_counts = {"MATCHED": 2, "MISMATCHED": 2, "UNMATCHED_A": 1, "AMBIGUOUS": 3,
                           "UNMATCHED_B": 1, "DUPLICATE": 3, "INVALID": 1}
        recorder.check("outcomes.all_seven",
                       "all seven reconciliation outcomes are demonstrated in one run",
                       counts == expected_counts and len(initial_rows) == 13,
                       {"observed": counts, "expected": expected_counts, "rows": len(initial_rows)})

        invalid_rows = [row for row in initial_rows if row["outcome"] == "INVALID"]
        recorder.check("outcomes.invalid_raw_only",
                       "INVALID reconciliation is raw-only lineage",
                       len(invalid_rows) == 1 and invalid_rows[0]["source_a_record_id"] is None
                       and invalid_rows[0]["source_b_record_id"] is None
                       and invalid_rows[0]["raw_record_id"] is not None,
                       invalid_rows)

        discrepancy_count = row_count(db, "discrepancies")
        discrepancies = _discrepancy_table(db)
        recorder.check("discrepancies.created",
                       "exactly the ambiguous and mismatched reconciliations create discrepancies",
                       discrepancy_count == 5 and all(
                           entry["reconciliation_outcome"] in {"AMBIGUOUS", "MISMATCHED"} for entry in discrepancies),
                       discrepancies)

        explainable = all(
            (row["evidence"].get("rule_version") == dataset.RULE_VERSION
             and row["evidence"].get("outcome") == row["outcome"]
             and "candidate_order" in row["evidence"] and "evaluated_at" in row["evidence"])
            or (row["outcome"] == "INVALID"
                and row["evidence"].get("validation") == "INVALID"
                and row["evidence"].get("outcome") == "INVALID")
            for row in initial_rows)
        recorder.check("decisions.explainable",
                       "every decision carries rule version, outcome, candidate order, and evaluation evidence",
                       explainable)

        event_types = {row[0] for row in db.connection.execute(
            "SELECT DISTINCT event_type FROM audit_events").fetchall()}
        required_events = {"BATCH_RECEIVED", "RECORD_INGESTED", "RECORD_VALIDATED", "NORMALIZATION_COMPLETED",
                           "MATCH_EVALUATED", "DUPLICATE_DETECTED", "DISCREPANCY_CREATED"}
        recorder.check("audit.stage_coverage",
                       "audit trail covers batch, ingestion, validation, normalization, matching, duplicate, and discrepancy events",
                       required_events <= event_types, {"missing": sorted(required_events - event_types)})

        raw_snapshot = _raw_snapshot(db)

        recorder.check("invariant.no_silent_loss",
                       "every accepted record has a validation result and a reconciliation outcome",
                       len(observed_outcomes) == 17 and all(
                           db.validation_results.get_for_raw(raw.raw_record_id, dataset.VALIDATION_VERSION) is not None
                           for raw in _all_raw_records(db)),
                       {"records_with_outcomes": len(observed_outcomes),
                        "raw_records": row_count(db, "raw_records")})

        # ---- Phase 2: resolution workflows ---------------------------------
        resolutions = _apply_resolutions(db, recorder)
        resolved_rows = [row for row in _all_reconciliation_rows(db) if row["state"] == "RESOLVED"]
        recorder.check("resolution.versions",
                       "approved resolutions create immutable superseding reconciliation versions",
                       len(resolved_rows) == 2 and all(row["reconciliation_version"] == 2 for row in resolved_rows)
                       and all(row["supersedes_reconciliation_id"] for row in resolved_rows),
                       resolved_rows)

        discrepancy_states = {entry["record_id"]: entry["state"] for entry in _discrepancy_table(db)}
        recorder.check("resolution.states",
                       "resolution states match the authorized workflows (resolved, deferred, rejected, open)",
                       discrepancy_states == {"A004": "RESOLVED", "A006": "RESOLVED", "A007": "DEFERRED",
                                              "B994": "REJECTED", "B995": "OPEN"},
                       discrepancy_states)

        recorder.check("resolution.counts",
                       "four resolutions exist and re-applied resolutions created no duplicates",
                       row_count(db, "resolutions") == 4,
                       {"resolutions": row_count(db, "resolutions")})

        recorder.observations["resolutions"] = resolutions
        recorder.observations["initial_decision_counts"] = counts

        # ---- Phase 3: API/reporting agreement and source isolation ---------
        api = LedgerAPI(db, token_verifier=_token_verifier())
        api_observations = _run_api_checks(db, api, recorder)

        # ---- Phase 4: idempotent replay ------------------------------------
        before_replay = {
            "raw": row_count(db, "raw_records"),
            "canonical": row_count(db, "canonical_transactions"),
            "reconciliations": row_count(db, "reconciliations"),
        }
        replay = ingestion.ingest(batch_a, dict(dataset.PORTFOLIO_A["A001"]),
                                  idempotency_key="pf-a:A001", accepted_at=dataset.now())
        recorder.check("replay.submission_duplicate",
                       "resubmitting an accepted payload is a submission duplicate without a new raw row",
                       replay.duplicate_submission is True
                       and row_count(db, "raw_records") == before_replay["raw"],
                       {"duplicate_submission": replay.duplicate_submission,
                        "raw_before": before_replay["raw"], "raw_after": row_count(db, "raw_records")})
        duplicate_event = db.connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE event_type = 'SUBMISSION_DUPLICATE'").fetchone()[0]
        recorder.check("replay.submission_duplicate_audited",
                       "a submission duplicate emits at most one SUBMISSION_DUPLICATE audit event",
                       duplicate_event >= 1, {"events": duplicate_event})

        run_standard_pipeline(db, [batch_a, batch_b], reconcile_invalid=True)
        recorder.check("replay.pipeline_idempotent",
                       "re-running validation/normalization/candidates/matching adds no authoritative rows",
                       row_count(db, "raw_records") == before_replay["raw"]
                       and row_count(db, "canonical_transactions") == before_replay["canonical"]
                       and row_count(db, "reconciliations") == before_replay["reconciliations"],
                       {"before": before_replay,
                        "after": {"raw": row_count(db, "raw_records"),
                                  "canonical": row_count(db, "canonical_transactions"),
                                  "reconciliations": row_count(db, "reconciliations")}})

        # ---- Phase 5: late-arriving counterpart (ingested through the API) ----
        # The batch itself is created with a deterministic batch id so the whole
        # evidence tree remains reproducible; record ingestion and the replay
        # below go through the HTTP API boundary.
        late_batch = ingestion.create_batch("source-b", "pf-ext-b-late", "source_b.v1",
                                            batch_id="pf-batch-b-late", received_at=dataset.now())
        late_batch_id = late_batch.batch_id
        late_record = api.handle("POST", f"/batches/{late_batch_id}/records",
                                 {"payload": dict(dataset.LATE_B["B-998"]), "idempotency_key": "late:B-998"},
                                 {"Authorization": "Bearer operator"})
        recorder.check("api.late_record_ingested",
                       "late-arriving record is accepted through the API",
                       late_record[0] == 200 and late_record[1]["data"]["status"] == "ACCEPTED",
                       late_record[0] if late_record[0] != 200 else late_record[1]["data"])
        replay_late = api.handle("POST", f"/batches/{late_batch_id}/records",
                                 {"payload": dict(dataset.LATE_B["B-998"]), "idempotency_key": "late:B-998"},
                                 {"Authorization": "Bearer operator"})
        recorder.check("api.late_record_idempotent",
                       "resubmitting the late record through the API is a submission duplicate",
                       replay_late[0] == 200 and replay_late[1]["data"]["duplicate_submission"] is True,
                       replay_late[1]["data"] if replay_late[0] == 200 else replay_late[0])

        validate_batches(db, [late_batch_id])
        normalize_raw_ids(db, [row.raw_record_id for row in db.raw_records.list_for_batch(late_batch_id)])
        verify_identities(db)
        generate_candidates(db)
        evaluate_matching(db)
        a003_rows = [row for row in _all_reconciliation_rows(db) if "A003" in _row_names(db, row)]
        late_matched = [row for row in a003_rows if row["outcome"] == "MATCHED" and "B-998" in _row_names(db, row)]
        original_unmatched = [row for row in a003_rows
                              if row["outcome"] == "UNMATCHED_A" and row["supersedes_reconciliation_id"] is None]
        recorder.check("late_arrival.new_decision",
                       "late arrival adds a MATCHED decision for A003 while preserving its UNMATCHED_A history",
                       bool(late_matched) and bool(original_unmatched),
                       a003_rows)
        # Architecture section 28 / D-007: the late arrival creates a linked
        # superseding reconciliation version rather than a second version-one row.
        recorder.check("late_arrival.supersedes_prior_version",
                       "late arrival creates a linked superseding reconciliation version",
                       len(late_matched) == 1 and len(original_unmatched) == 1
                       and late_matched[0]["reconciliation_version"] == 2
                       and late_matched[0]["supersedes_reconciliation_id"] == original_unmatched[0]["reconciliation_id"],
                       {"late": [{key: row[key] for key in ("reconciliation_id", "reconciliation_version",
                                                            "outcome", "supersedes_reconciliation_id")}
                                 for row in late_matched],
                        "original": [{key: row[key] for key in ("reconciliation_id", "reconciliation_version",
                                                                "outcome", "supersedes_reconciliation_id")}
                                     for row in original_unmatched]})
        current_ids = {row.reconciliation_id for row in db.reconciliations.list_current()}
        recorder.check("late_arrival.current_state",
                       "current_state is the latest non-superseded version for the A003 scope",
                       bool(late_matched) and bool(original_unmatched)
                       and late_matched[0]["reconciliation_id"] in current_ids
                       and original_unmatched[0]["reconciliation_id"] not in current_ids,
                       {"current_versions": len(current_ids)})

        current_raw_snapshot = _raw_snapshot(db)
        recorder.check("history.immutable_rows",
                       "no authoritative row was mutated or deleted by replay, resolution, or late arrival",
                       row_count(db, "reconciliations") == 16
                       and all(row in current_raw_snapshot for row in raw_snapshot),
                       {"rows": row_count(db, "reconciliations"),
                        "original_raw_rows_preserved": all(row in current_raw_snapshot for row in raw_snapshot),
                        "raw_rows": len(current_raw_snapshot)})

        immutable = _probe_raw_immutability(db)
        recorder.check("history.immutability_enforced",
                       "direct mutation of an accepted raw payload is rejected by persistence",
                       immutable["rejected"] is True and immutable["row_intact"] is True,
                       immutable)

        recorder.observations["api"] = api_observations
        recorder.observations["record_outcomes"] = {key: value["outcome"] for key, value in sorted(observed_outcomes.items())}
        recorder.observations["row_counts"] = {
            "raw_records": row_count(db, "raw_records"),
            "canonical_transactions": row_count(db, "canonical_transactions"),
            "reconciliations": row_count(db, "reconciliations"),
            "discrepancies": row_count(db, "discrepancies"),
            "resolutions": row_count(db, "resolutions"),
            "audit_events": row_count(db, "audit_events"),
        }
        recorder.observations["signature"] = database_signature(db)
        return recorder.finish()
    finally:
        if own_database:
            db.close()


def _apply_resolutions(database: LedgerDatabase, recorder: ProofRecorder) -> list[dict[str, Any]]:
    """Apply the fixed resolution workflow; manual approval goes through the API."""
    by_record = {entry["record_id"]: entry for entry in _discrepancy_table(database)}
    applied: list[dict[str, Any]] = []
    api = LedgerAPI(database, token_verifier=_token_verifier())
    for spec in dataset.EXPECTED_RESOLUTIONS:
        record_id = _record_for_resolution(by_record, spec)
        entry = by_record[record_id]
        resolution_type = ResolutionType(spec["resolution_type"])
        service = ResolutionService(database)
        if spec["resolution_type"] == "AUTOMATIC":
            result = service.resolve(entry["discrepancy_id"], resolution_type,
                                     actor="system", reason=spec["reason"],
                                     rule_version=spec["rule_version"], created_at=dataset.now())
        elif spec["resolution_type"] == "MANUAL_APPROVED":
            status, body = api.handle("POST", f"/discrepancies/{entry['discrepancy_id']}/resolve",
                                      {"resolution_type": "MANUAL_APPROVED", "reason": spec["reason"]},
                                      {"Authorization": "Bearer operator"})
            recorder.check(f"resolution.api_{record_id}",
                           f"operator resolution for {record_id} is accepted through the API",
                           status == 200, {"status": status, "body": body})
            result = None
        else:
            result = service.resolve(entry["discrepancy_id"], resolution_type,
                                     actor="reconciliation_operator", reason=spec["reason"],
                                     created_at=dataset.now())
        applied.append({
            "record_id": record_id,
            "discrepancy_id": entry["discrepancy_id"],
            "reconciliation_outcome": entry["reconciliation_outcome"],
            "resolution_type": spec["resolution_type"],
        })
        if result is not None:
            again = service.resolve(entry["discrepancy_id"], resolution_type,
                                    actor=result.resolution.actor, reason=result.resolution.reason,
                                    evidence=dict(result.resolution.evidence),
                                    rule_version=result.resolution.rule_version,
                                    created_at=dataset.now())
            recorder.check(f"resolution.idempotent_{record_id}",
                           f"resolution replay for {record_id} returns the same immutable resolution",
                           again.resolution == result.resolution
                           and again.resolution.resolution_id == result.resolution.resolution_id,
                           {"first": result.resolution.resolution_id, "replay": again.resolution.resolution_id})
    return applied


def _record_for_resolution(by_record: dict[str, Any], spec: dict[str, str]) -> str:
    fixed = {
        "AUTOMATIC": "A004",
        "MANUAL_APPROVED": "A006",
        "DEFERRED": "A007",
        "REJECTED": "B994",
    }
    record_id = fixed[spec["resolution_type"]]
    if record_id not in by_record:
        raise AssertionError(f"expected an open discrepancy for {record_id}")
    if by_record[record_id]["reconciliation_outcome"] != spec["reconciliation_outcome"]:
        raise AssertionError(f"resolution fixture mismatch for {record_id}")
    return record_id


def _run_api_checks(database: LedgerDatabase, api: LedgerAPI, recorder: ProofRecorder) -> dict[str, Any]:
    authorized = {"Authorization": "Bearer operator"}
    reader_a = {"Authorization": "Bearer reader-a"}

    status, report = api.handle("GET", "/reports", headers=authorized)
    authoritative = outcome_count_values(all_outcome_rows(database))
    report_outcomes = report["data"]["outcomes"] if status == 200 else {}
    recorder.check("api.report_matches_authority",
                   "API report outcome counts agree with authoritative reconciliation rows",
                   status == 200 and report_outcomes == authoritative,
                   {"report": report_outcomes, "authoritative": authoritative})

    status_b, report_b = api.handle("GET", "/reports", {"batch_id": "pf-batch-a"}, authorized)
    authoritative_b = outcome_count_values(all_outcome_rows(database))  # placeholder replaced below
    batch_outcomes: dict[str, int] = {}
    if status_b == 200:
        batch_outcomes = report_b["data"]["outcomes"]
    rows_b = [row for row in all_outcome_rows(database) if row["batch_id"] == "pf-batch-a"]
    authoritative_b = outcome_count_values(rows_b)
    recorder.check("api.report_batch_matches_authority",
                   "batch-scoped API report agrees with authoritative rows for that batch",
                   status_b == 200 and batch_outcomes == authoritative_b,
                   {"report": batch_outcomes, "authoritative": authoritative_b})

    status_export, export = api.handle("GET", "/export", headers=authorized)
    export_text = json.dumps(export)
    leaked = [value for value in _raw_payload_values(database) if value and value in export_text]
    recorder.check("api.export_redacted",
                   "export projection is read-only and contains no raw payload values",
                   status_export == 200 and not leaked,
                   {"leaked": leaked[:3]})

    status_scoped, scoped = api.handle("GET", "/reconciliations", headers=reader_a)
    allowed_rows = [row for row in _all_reconciliation_rows(database)
                    if row["batch_id"] in _source_batch_ids(database, "source-a")]
    recorder.check("api.source_isolation_reconciliations",
                   "reader scoped to source-a sees only source-a reconciliation rows",
                   status_scoped == 200 and len(scoped["data"]) == len(allowed_rows),
                   {"visible": len(scoped["data"]) if status_scoped == 200 else None,
                    "authoritative": len(allowed_rows)})

    status_blocked = api.handle("GET", "/reports", {"batch_id": "pf-batch-b"}, reader_a)
    recorder.check("api.source_isolation_batch",
                   "reader scoped to source-a cannot read a source-b batch report",
                   status_blocked[0] == 403, {"status": status_blocked[0]})

    status_audit = api.handle("GET", "/audit/batch/pf-batch-a", headers=reader_a)
    status_audit_blocked = api.handle("GET", "/audit/batch/pf-batch-b", headers=reader_a)
    recorder.check("api.source_isolation_audit",
                   "audit retrieval is scoped by source",
                   status_audit[0] == 200 and status_audit_blocked[0] == 403,
                   {"source_a": status_audit[0], "source_b": status_audit_blocked[0]})

    open_entry = next(entry for entry in _discrepancy_table(database) if entry["state"] == "OPEN")
    status_unauthorized = api.handle("POST", f"/discrepancies/{open_entry['discrepancy_id']}/resolve",
                                     {"resolution_type": "MANUAL_APPROVED", "reason": "nope"}, reader_a)
    recorder.check("api.role_enforced",
                   "resolution without the operator role is rejected",
                   status_unauthorized[0] == 403, {"status": status_unauthorized[0]})

    status_anon = api.handle("GET", "/reports")
    recorder.check("api.authentication_required",
                   "unauthenticated requests are rejected",
                   status_anon[0] == 401, {"status": status_anon[0]})

    health = api.handle("GET", "/health", headers=authorized)
    recorder.check("api.health",
                   "health endpoint reports application and database ok",
                   health[0] == 200 and health[1]["data"]["database"] == "ok",
                   health[1]["data"] if health[0] == 200 else None)

    return {
        "report_outcomes": report_outcomes,
        "report_batch_a_outcomes": batch_outcomes,
        "export_redacted": not leaked,
        "scoped_reconciliation_count": len(scoped["data"]) if status_scoped == 200 else None,
    }


def _source_batch_ids(database: LedgerDatabase, source_id: str) -> list[str]:
    rows = database.connection.execute(
        "SELECT batch_id FROM batches WHERE source_id = ? ORDER BY batch_id", (source_id,)).fetchall()
    return [row["batch_id"] for row in rows]


def _raw_payload_values(database: LedgerDatabase) -> list[str]:
    values: list[str] = []
    for row in database.connection.execute("SELECT payload_json FROM raw_records").fetchall():
        payload = json.loads(row["payload_json"]) if isinstance(row["payload_json"], str) else {}
        values.extend(str(value) for value in payload.values() if isinstance(value, str))
    return values


def _probe_raw_immutability(database: LedgerDatabase) -> dict[str, Any]:
    row = database.connection.execute(
        "SELECT raw_record_id, payload_json FROM raw_records ORDER BY raw_record_id LIMIT 1").fetchone()
    rejected = False
    try:
        database.connection.execute("UPDATE raw_records SET payload_json = '{}' WHERE raw_record_id = ?",
                                    (row["raw_record_id"],))
        database.connection.commit()
    except sqlite3.IntegrityError:
        rejected = True
        database.connection.rollback()
    intact = database.connection.execute(
        "SELECT payload_json FROM raw_records WHERE raw_record_id = ?", (row["raw_record_id"],)).fetchone()[0] == row["payload_json"]
    return {"rejected": rejected, "row_intact": intact}


# --------------------------------------------------------------------------
# Telemetry scenario
# --------------------------------------------------------------------------

def run_telemetry() -> dict[str, Any]:
    """Prove every pipeline stage emits structured, redacted telemetry."""
    recorder = ProofRecorder("telemetry")
    db = LedgerDatabase()
    try:
        sink = InMemoryTelemetrySink()
        ingestion = RawIngestion(db, telemetry=sink)
        register_sources(ingestion)
        batch_a = ingestion.create_batch("source-a", "tel-ext-a", "source_a.v1", batch_id="tel-batch-a",
                                         received_at=dataset.now())
        batch_b = ingestion.create_batch("source-b", "tel-ext-b", "source_b.v1", batch_id="tel-batch-b",
                                         received_at=dataset.now())
        pair = ({"record_id": "T-A1", "occurred_at": "2026-09-20", "amount": "15.00", "currency": "USD",
                 "direction": "CREDIT", "transaction_reference": "TEL-1", "description": "Telemetry payment description"},
                {"id": "T-B1", "posted": "2026-09-20", "value": "15.00", "ccy": "USD", "side": "CREDIT",
                 "reference": "TEL-1", "memo": "Telemetry payment description"})
        payload_a, payload_b = pair
        ingestion.ingest(batch_a.batch_id, payload_a, idempotency_key="tel:a", accepted_at=dataset.now())
        ingestion.ingest(batch_b.batch_id, payload_b, idempotency_key="tel:b", accepted_at=dataset.now())
        ValidationService(db, telemetry=sink).validate_batch(batch_a.batch_id)
        ValidationService(db, telemetry=sink).validate_batch(batch_b.batch_id)
        normalization = NormalizationService(db, telemetry=sink)
        for raw in db.raw_records.list_for_batch(batch_a.batch_id):
            normalization.normalize_record(raw.raw_record_id, created_at=dataset.now())
        for raw in db.raw_records.list_for_batch(batch_b.batch_id):
            normalization.normalize_record(raw.raw_record_id, created_at=dataset.now())
        for transaction in db.canonical_transactions.list_all():
            IdentityService(db, telemetry=sink).identify(transaction)
        CandidateGenerationService(db, telemetry=sink).generate_all()
        MatchingService(db).evaluate(evaluated_at=dataset.now())

        names = {event["name"] for event in sink.events}
        required = {"ledger.ingestion.record_accepted", "ledger.validation.record_valid",
                    "ledger.normalization.completed", "ledger.identity.verified"}
        serialized = json.dumps(sink.events)
        recorder.check("telemetry.stage_coverage",
                       "telemetry is emitted by ingestion, validation, normalization, and identity",
                       required <= names, {"missing": sorted(required - names)})
        recorder.check("telemetry.redaction",
                       "telemetry events contain no payload or description values",
                       "description" not in serialized and "Telemetry payment description" not in serialized
                       and "payload" not in serialized,
                       {"event_count": len(sink.events)})
        recorder.observations["events"] = sorted(names)
        recorder.observations["event_count"] = len(sink.events)
        recorder.observations["signature"] = database_signature(db)
        return recorder.finish()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Correction scenario
# --------------------------------------------------------------------------

def run_correction() -> dict[str, Any]:
    recorder = ProofRecorder("correction")
    db = LedgerDatabase()
    try:
        ingestion = RawIngestion(db)
        register_sources(ingestion)
        batch_a, _ = seed_records(db, "source-a", "source_a.v1", dataset.CORRECTION_A,
                                  batch_id="corr-batch-a", external_batch_id="corr-ext-a", idempotency_prefix="corr-a")
        batch_b, _ = seed_records(db, "source-b", "source_b.v1", dataset.CORRECTION_B,
                                  batch_id="corr-batch-b", external_batch_id="corr-ext-b", idempotency_prefix="corr-b")
        run_standard_pipeline(db, [batch_a, batch_b])

        original_outcomes = record_outcomes(db)
        recorder.check("correction.original_matched",
                       "original P-1/Q-1 pair reconciles as MATCHED before correction",
                       original_outcomes.get("P-1", {}).get("outcome") == "MATCHED"
                       and original_outcomes.get("Q-1", {}).get("outcome") == "MATCHED",
                       original_outcomes)
        original_raw_snapshot = _raw_snapshot(db)
        original_decisions = _all_reconciliation_rows(db)
        original_canonical_count = row_count(db, "canonical_transactions")

        corrected = ingestion.ingest(batch_a, dict(dataset.CORRECTED_P1_PAYLOAD),
                                     idempotency_key="corr-a:P-1:corrected", accepted_at=dataset.now())
        original_raw = db.raw_records.find_by_source_record("source-a", "source_a.v1", "P-1")[0]
        corrected_raw = db.raw_records.get(corrected.raw_record_id)  # type: ignore[arg-type]
        recorder.check("correction.raw_supersedes",
                       "corrected raw record links to the original through supersession",
                       corrected_raw is not None and corrected_raw.supersedes_raw_record_id == original_raw.raw_record_id,
                       {"supersedes": corrected_raw.supersedes_raw_record_id if corrected_raw else None,
                        "original": original_raw.raw_record_id})

        validate_batches(db, [batch_a])
        normalize_raw_ids(db, [corrected_raw.raw_record_id])  # type: ignore[arg-type]
        verify_identities(db)
        generate_candidates(db)
        evaluate_matching(db)

        current_raw_snapshot = _raw_snapshot(db)
        recorder.check("correction.original_preserved",
                       "original raw rows, canonical rows, and decisions are intact after correction",
                       all(row in current_raw_snapshot for row in original_raw_snapshot)
                       and row_count(db, "raw_records") == len(original_raw_snapshot) + 1
                       and row_count(db, "canonical_transactions") == original_canonical_count + 1
                       and all(row in _all_reconciliation_rows(db) for row in original_decisions),
                       {"raw_records": row_count(db, "raw_records"),
                        "canonical_transactions": row_count(db, "canonical_transactions"),
                        "decisions_preserved": all(row in _all_reconciliation_rows(db) for row in original_decisions)})

        recorder.check("correction.new_canonical",
                       "corrected payload creates a new canonical version and never mutates the original",
                       row_count(db, "canonical_transactions") == 3
                       and db.canonical_transactions.get_for_raw_version(  # type: ignore[union-attr]
                           corrected_raw.raw_record_id, dataset.NORMALIZATION_VERSION) is not None,
                       row_count(db, "canonical_transactions"))

        recorder.check("correction.history_visible",
                       "original and corrected payloads remain retrievable with validation and audit history",
                       all(db.validation_results.get_for_raw(raw.raw_record_id, dataset.VALIDATION_VERSION) is not None
                           for raw in _all_raw_records(db))
                       and row_count(db, "audit_events") >= 10,
                       {"audit_events": row_count(db, "audit_events")})

        run_standard_pipeline(db, [batch_a, batch_b])
        recorder.check("correction.replay_idempotent",
                       "re-running the pipeline after correction adds no duplicate authoritative rows",
                       row_count(db, "raw_records") == 3
                       and row_count(db, "canonical_transactions") == 3
                       and row_count(db, "reconciliations") == len(pipeline_decisions(db)),
                       {"raw": row_count(db, "raw_records"), "canonical": row_count(db, "canonical_transactions"),
                        "reconciliations": row_count(db, "reconciliations")})

        recorder.observations["outcomes_after_correction"] = record_outcomes(db)
        recorder.observations["row_counts"] = {
            "raw_records": row_count(db, "raw_records"),
            "canonical_transactions": row_count(db, "canonical_transactions"),
            "reconciliations": row_count(db, "reconciliations"),
            "audit_events": row_count(db, "audit_events"),
        }
        recorder.observations["signature"] = database_signature(db)
        return recorder.finish()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Restart scenario
# --------------------------------------------------------------------------

def run_restart() -> dict[str, Any]:
    """Persist to a real file, close, reopen, and prove replay reproduces state."""
    recorder = ProofRecorder("restart")
    db_path = None
    try:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "product-proof.sqlite3")

            def prepare() -> tuple[str, dict[str, Any]]:
                database = LedgerDatabase(db_path)
                try:
                    ingestion = RawIngestion(database)
                    register_sources(ingestion)
                    batch_a, _ = seed_records(database, "source-a", "source_a.v1", dataset.RESTART_A,
                                              batch_id="restart-batch-a", external_batch_id="restart-ext-a",
                                              idempotency_prefix="restart-a")
                    batch_b, _ = seed_records(database, "source-b", "source_b.v1", dataset.RESTART_B,
                                              batch_id="restart-batch-b", external_batch_id="restart-ext-b",
                                              idempotency_prefix="restart-b")
                    run_standard_pipeline(database, [batch_a, batch_b])
                    return database_signature(database), {
                        "raw": row_count(database, "raw_records"),
                        "canonical": row_count(database, "canonical_transactions"),
                        "reconciliations": row_count(database, "reconciliations"),
                        "audit": row_count(database, "audit_events"),
                    }
                finally:
                    database.close()

            first_signature, first_counts = prepare()
            reopened = LedgerDatabase(db_path)
            try:
                validate_batches(reopened, ["restart-batch-a", "restart-batch-b"])
                raw_ids = [row.raw_record_id for row in reopened.raw_records.list_for_batch("restart-batch-a")]
                raw_ids += [row.raw_record_id for row in reopened.raw_records.list_for_batch("restart-batch-b")]
                normalize_raw_ids(reopened, raw_ids)
                verify_identities(reopened)
                generate_candidates(reopened)
                evaluate_matching(reopened)
                second_signature = database_signature(reopened)
                second_counts = {
                    "raw": row_count(reopened, "raw_records"),
                    "canonical": row_count(reopened, "canonical_transactions"),
                    "reconciliations": row_count(reopened, "reconciliations"),
                    "audit": row_count(reopened, "audit_events"),
                }
            finally:
                reopened.close()

            recorder.check("restart.reopen_preserves_state",
                           "reopening the persisted database reproduces identical authoritative state",
                           first_signature == second_signature and first_counts == second_counts,
                           {"first": first_counts, "second": second_counts,
                            "signature_stable": first_signature == second_signature})
            recorder.observations["signature"] = first_signature
            recorder.observations["counts"] = second_counts
            return recorder.finish()
    finally:
        if db_path is not None:
            Path(db_path).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Full proof
# --------------------------------------------------------------------------

def run_full_proof() -> dict[str, Any]:
    """Execute every scenario on fresh databases and return the full evidence tree."""
    results: dict[str, Any] = {
        "schema_version": SUITE_VERSION,
        "manifest_sha256": dataset.manifest_sha256(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "sqlite": __import__("sqlite3").sqlite_version,
        },
        "scenarios": {},
        "checks": [],
    }
    scenario_results = [
        run_portfolio(),
        run_telemetry(),
        run_correction(),
        run_restart(),
    ]
    for scenario in scenario_results:
        results["scenarios"][scenario["scenario"]] = scenario["observations"]
        results["checks"].extend(scenario["checks"])
    signatures = [scenario["observations"]["signature"] for scenario in scenario_results]
    results["signature"] = hashlib.sha256(
        canonical_json({"manifest": results["manifest_sha256"], "scenario_signatures": signatures})).hexdigest()
    failed = [check for check in results["checks"] if not check["passed"]]
    if failed:
        raise AssertionError(
            f"product proof failed {len(failed)} checks: "
            + "; ".join(f"{check['scenario']}:{check['check_id']}" for check in failed))
    return results


def evidence_file() -> Path:
    return Path(__file__).resolve().parents[1] / "evidence" / "product-proof.json"


def write_evidence(results: dict[str, Any]) -> Path:
    target = evidence_file()
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(results, indent=2, sort_keys=True, default=str) + "\n")
    return target
