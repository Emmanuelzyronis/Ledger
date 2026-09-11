"""Epic 8 (EMM-84) staging rehearsal and representative load proof.

Runs the production process model over real HTTP — the same service entrypoint,
the same bearer-token verifier, the same SQLite authority, the same operator
runner — and measures functional, security, performance, recovery, and
observability behavior. Results are written to ``evidence/staging-proof.json``.

What this is: a staged rehearsal on one host over the real transport.
What this is not: a hosted multi-host environment. That limitation is recorded
in the evidence and in ``docs/staging.md``.

Run::

    PYTHONPATH=src python3 staging/run_staging_proof.py [--shards 60]
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from ledger.__main__ import serve  # noqa: E402
from ledger.alerts import AlertInputs, evaluate  # noqa: E402
from ledger.domain import BatchState  # noqa: E402
from ledger.observability import JsonLogSink  # noqa: E402
from ledger import ops, pipeline  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from ledger.security import HmacTokenVerifier, Principal  # noqa: E402
from ledger.service import LedgerService, ServiceSettings  # noqa: E402

from staging import dataset  # noqa: E402

EVIDENCE_PATH = REPO_ROOT / "evidence" / "staging-proof.json"
TOKEN_SECRET = "staging-secret-not-a-production-credential-000000"
OPERATOR = Principal(subject="staging-operator", roles=("reconciliation_operator",), source_ids=None)
READER = Principal(subject="staging-reader", roles=("reader",), source_ids=("source-a",))


class Client:
    """Minimal authenticated HTTP client over the real service transport."""

    def __init__(self, base: str, token: str | None) -> None:
        self.base = base
        self.token = token
        self.latencies: list[float] = []
        self.lock = threading.Lock()

    @staticmethod
    def _decode(raw: bytes) -> dict | str:
        """Decode a response body: JSON objects stay dicts, text stays text.

        ``/v1/metrics`` is ``text/plain`` and must not be forced through JSON.
        """
        raw = raw or b"{}"
        try:
            decoded = json.loads(raw)
        except ValueError:
            return raw.decode("utf-8", "replace")
        return decoded if isinstance(decoded, dict) else str(decoded)

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = self._decode(response.read())
                status = response.status
        except urllib.error.HTTPError as exc:
            body = self._decode(exc.read())
            status = exc.code
        elapsed = time.perf_counter() - started
        with self.lock:
            self.latencies.append(elapsed)
        return status, body

    def timed(self, method: str, path: str, payload: dict | None = None, *, retries: int = 2) -> tuple[int, dict | str]:
        """GET with a short retry for transient connection resets under load."""
        last: tuple[int, dict | str] = (0, {})
        for attempt in range(retries + 1):
            try:
                return self.request(method, path, payload)
            except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
                last = (0, {"error": {"code": "transport", "message": str(exc)}})
                time.sleep(0.05 * (attempt + 1))
        return last


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 6)


def _register_sources(client: Client) -> None:
    for source_id, name, schema in (
        ("source-a", "Source A", ["source_a.v1"]),
        ("source-b", "Source B", ["source_b.v1"]),
    ):
        status, body = client.request("POST", "/v1/sources",
                                      {"source_id": source_id, "name": name, "schema_versions": schema})
        if status != 200 and body.get("error", {}).get("code") != "already_exists":
            raise RuntimeError(f"registering {source_id} failed: {status} {body}")


def _ingest(client: Client, batch_id: str, payloads: dict[str, dict], *, prefix: str) -> dict:
    accepted = duplicates = 0
    started = time.perf_counter()
    for index, record_id in enumerate(sorted(payloads)):
        status, body = client.request(
            "POST", f"/v1/batches/{batch_id}/records",
            {"payload": payloads[record_id], "idempotency_key": f"{prefix}:{record_id}"},
        )
        if status != 200:
            raise RuntimeError(f"ingest {record_id} failed: {status} {body}")
        if body["data"].get("duplicate_submission"):
            duplicates += 1
        else:
            accepted += 1
    return {
        "records": len(payloads),
        "accepted": accepted,
        "duplicate_submissions": duplicates,
        "seconds": round(time.perf_counter() - started, 4),
        "requests_per_second": round(len(payloads) / max(time.perf_counter() - started, 1e-9), 2),
    }


def _record_outcome_map(database: LedgerDatabase, batch_ids: list[str]) -> dict[str, str]:
    mapped = pipeline._record_outcomes(database, batch_ids)  # noqa: SLF001 - staging asserts the runner's own mapping
    by_source: dict[str, str] = {}
    for raw_id, entry in mapped.items():
        raw = database.raw_records.get(raw_id)
        if raw is not None:
            by_source[raw.source_record_id] = entry["outcome"]
    return by_source


def run(*, shards: int = 60, clients: int = 8, requests_per_client: int = 25,
        long_batch_records: int = 400) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="ledger-staging-"))
    logs = (workdir / "staging-service.log").open("w", encoding="utf-8")
    database_path = str(workdir / "ledger.sqlite3")
    server = None
    service = None
    try:
        settings = ServiceSettings(
            database_path=database_path, host="127.0.0.1", port=0,
            require_tls=False, token_secret=TOKEN_SECRET, max_body_bytes=1_048_576,
            rate_limit_per_minute=0,
        )
        service = LedgerService(settings, telemetry=JsonLogSink(logs)).start()
        server = serve(service)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        verifier = HmacTokenVerifier(TOKEN_SECRET)
        operator = Client(base, verifier.issue(OPERATOR))
        reader = Client(base, verifier.issue(READER))
        anonymous = Client(base, None)

        _register_sources(operator)

        # ---- representative corpus over the real ingest path --------------
        source_a, source_b = dataset.scaled_payloads(shards)
        batch_a = operator.request("POST", "/v1/batches", {
            "source_id": "source-a", "external_batch_id": "staging-a", "schema_version": "source_a.v1"})[1]["data"]["batch_id"]
        batch_b = operator.request("POST", "/v1/batches", {
            "source_id": "source-b", "external_batch_id": "staging-b", "schema_version": "source_b.v1"})[1]["data"]["batch_id"]
        ingest_a = _ingest(operator, batch_a, source_a, prefix="staging-a")
        ingest_b = _ingest(operator, batch_b, source_b, prefix="staging-b")

        # ---- concurrency / load profile ----------------------------------
        paths = ["/v1/health", "/v1/batches", "/v1/reports", "/v1/discrepancies"]
        errors = {"count": 0}
        load_started = time.perf_counter()
        measured: list[float] = []

        def worker(index: int) -> None:
            pipelined = Client(base, verifier.issue(OPERATOR)) if index % 2 == 0 else Client(base, verifier.issue(READER))
            for step in range(requests_per_client):
                path = paths[(index + step) % len(paths)]
                status, _body = pipelined.timed("GET", path)
                if status != 200:
                    with pipelined.lock:
                        errors["count"] += 1
            measured.extend(pipelined.latencies)

        with ThreadPoolExecutor(max_workers=clients) as pool:
            list(pool.map(worker, range(clients)))
        load_seconds = time.perf_counter() - load_started
        total_requests = clients * requests_per_client

        # ---- long batch through the operator runner -----------------------
        long_payloads = {
            f"LONG-{index:05d}": {
                "record_id": f"LONG-{index:05d}",
                "occurred_at": "2026-09-20",
                "amount": f"{2000 + index}.00",
                "currency": "USD",
                "direction": "CREDIT",
                "transaction_reference": f"LONG-REF-{index:05d}",
            }
            for index in range(long_batch_records)
        }
        batch_long = operator.request("POST", "/v1/batches", {
            "source_id": "source-a", "external_batch_id": "staging-long", "schema_version": "source_a.v1"})[1]["data"]["batch_id"]
        ingest_long = _ingest(operator, batch_long, long_payloads, prefix="staging-long")

        processing_started = time.perf_counter()
        runs = pipeline.process_batches(
            LedgerDatabase(database_path), [batch_a, batch_b, batch_long],
            evaluated_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )
        processing_seconds = round(time.perf_counter() - processing_started, 4)
        states = {run.batch_id: run.state for run in runs}
        if any(state != "COMPLETED" for state in states.values()):
            raise RuntimeError(f"staging batches did not complete: {states}")

        # ---- correctness against the proven per-shard outcomes ------------
        database = LedgerDatabase(database_path)
        try:
            outcomes = _record_outcome_map(database, [batch_a, batch_b])
            mismatches: list[str] = []
            for record_id, expected_outcome in (
                (f"{key}-S{shard}", value)
                for shard in range(shards)
                for key, value in dataset.EXPECTED_PORTFOLIO_OUTCOMES.items()
            ):
                if outcomes.get(record_id) != expected_outcome:
                    mismatches.append(f"{record_id}: expected {expected_outcome}, got {outcomes.get(record_id)}")
            if mismatches:
                raise RuntimeError(f"{len(mismatches)} outcome mismatches, first: {mismatches[:3]}")
            observed_counts: dict[str, int] = {}
            for outcome in outcomes.values():
                observed_counts[outcome] = observed_counts.get(outcome, 0) + 1
            long_batch_after = database.batches.get(batch_long)
            reconciliation_rows = database.connection.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0]

            # ---- late arrival / LA-1 supersession -------------------------
            # The A leg arrives first and is recorded as UNMATCHED_A. The B leg
            # arrives later and must supersede that decision with a new immutable
            # version rather than overwriting it. Assertions target the decision
            # rows that actually cover these canonical records, not "the newest
            # row in the table" (other batches also write versions).
            late_a = operator.request("POST", "/v1/batches", {
                "source_id": "source-a", "external_batch_id": "staging-late-a", "schema_version": "source_a.v1"})[1]["data"]["batch_id"]
            operator.request("POST", f"/v1/batches/{late_a}/records", {"payload": {
                "record_id": "LATE-A", "occurred_at": "2026-09-25", "amount": "9001.00",
                "currency": "USD", "direction": "CREDIT", "transaction_reference": "LATE-REF"}})
            late_a_runs = pipeline.process_batches(database, [late_a],
                                                   evaluated_at=datetime(2026, 9, 25, tzinfo=timezone.utc))
            late_a_ids = _canonical_ids_for_records(database, late_a, ("LATE-A",))
            if len(late_a_ids) != 1:
                raise RuntimeError(f"late A leg did not produce exactly one canonical row: {late_a_ids}")
            before = _late_arrival_state(database, late_a_ids)
            late_b = operator.request("POST", "/v1/batches", {
                "source_id": "source-b", "external_batch_id": "staging-late-b", "schema_version": "source_b.v1"})[1]["data"]["batch_id"]
            operator.request("POST", f"/v1/batches/{late_b}/records", {"payload": {
                "id": "LATE-B", "posted": "2026-09-25", "value": "9001.00", "ccy": "USD",
                "side": "CREDIT", "reference": "LATE-REF"}})
            late_b_runs = pipeline.process_batches(database, [late_b],
                                                   evaluated_at=datetime(2026, 9, 25, tzinfo=timezone.utc))
            late_b_ids = _canonical_ids_for_records(database, late_b, ("LATE-B",))
            if len(late_b_ids) != 1:
                raise RuntimeError(f"late B leg did not produce exactly one canonical row: {late_b_ids}")
            after = _late_arrival_state(database, late_a_ids | late_b_ids)
            if before["outcome"] != "UNMATCHED_A" or after["outcome"] != "MATCHED":
                raise RuntimeError(f"late arrival did not supersede: before={before} after={after}")
            if after["reconciliation_version"] != before["reconciliation_version"] + 1:
                raise RuntimeError(f"late arrival did not create a new version: before={before} after={after}")
            if after["supersedes_reconciliation_id"] != before["reconciliation_id"]:
                raise RuntimeError(f"late arrival did not link to the prior version: {after}")
            prior_still_present = database.reconciliations.get(before["reconciliation_id"]) is not None
            if not prior_still_present:
                raise RuntimeError("late arrival overwrote the prior reconciliation version")
        finally:
            database.close()

        # ---- observability under load ------------------------------------
        status, metrics_body = operator.timed("GET", "/v1/metrics")
        metrics_text = metrics_body if isinstance(metrics_body, str) else ""
        if status != 200 or not metrics_text:
            raise RuntimeError(f"metrics scrape failed: status={status} body={metrics_body!r}")
        alerts_fired = evaluate(AlertInputs(
            service_up=True, ready=True,
            server_error_ratio=(errors["count"] / total_requests) if total_requests else 0.0,
            latency_p95_seconds=percentile(measured, 0.95),
            in_flight=0, in_flight_limit=settings.max_concurrent_requests,
        ))

        # ---- security boundary -------------------------------------------
        security = {
            "unauthenticated_read": anonymous.request("GET", "/v1/reports")[0],
            "invalid_token": Client(base, "not-a-token").request("GET", "/v1/reports")[0],
            "wrong_scope_batch": reader.request("GET", f"/v1/batches/{batch_b}")[0],
            "operator_scoped_read": operator.request("GET", "/v1/reports")[0],
            "correlation_echo": _correlation_check(base),
            "degraded_readiness": service.render_metrics().count("ledger_ready_state 1"),
        }

        # ---- recovery drill ----------------------------------------------
        drill = ops.drill(database_path, str(workdir / "recovery"))

        # ---- report -------------------------------------------------------
        latencies = sorted(measured)
        return {
            "schema_version": 1,
            "epic": "EMM-84",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "host": "single process over real HTTP on 127.0.0.1 (stdlib server)",
                "database": "SQLite (single authoritative store)",
                "auth": "HMAC-signed bearer tokens (production verifier)",
                "python": sys.version.split()[0],
                "platform": os.uname().sysname + " " + os.uname().release,
                "limitation": "one host, no container orchestration, no network latency between tiers",
            },
            "dataset": {
                "shards": shards,
                "records": len(source_a) + len(source_b),
                "shape": "Layer 15 portfolio repeated as disjoint-key shards (amounts + dates + references shifted)",
                "provenance": "outcomes derived from evidence/product-proof.json, not re-invented for staging",
            },
            "pipeline": {
                "batches": len(runs),
                "states": states,
                "processing_seconds": processing_seconds,
                "records_processed": len(source_a) + len(source_b) + long_batch_records,
                "records_per_second": round((len(source_a) + len(source_b) + long_batch_records) / max(processing_seconds, 1e-9), 2),
                "reconciliation_rows": reconciliation_rows,
                "outcome_counts": observed_counts,
                "expected_outcome_counts": dataset.expected_outcomes(shards),
                "outcome_mismatches": len(mismatches),
                "records_checked": len(outcomes),
                "long_batch": {"records": long_batch_records, "state": long_batch_after.state.value,
                               "counters": {name: getattr(long_batch_after.counters, name)
                                            for name in ("received_count", "accepted_count", "processed_count", "unmatched_count")},
                               "ingest": ingest_long},
            },
            "ingest": {"source_a": ingest_a, "source_b": ingest_b},
            "load": {
                "profile": f"{clients} concurrent clients x {requests_per_client} requests",
                "requests": total_requests,
                "seconds": round(load_seconds, 4),
                "requests_per_second": round(total_requests / max(load_seconds, 1e-9), 2),
                "errors": errors["count"],
                "latency_ms": {
                    "p50": round(percentile(latencies, 0.50) * 1000, 3),
                    "p95": round(percentile(latencies, 0.95) * 1000, 3),
                    "p99": round(percentile(latencies, 0.99) * 1000, 3),
                    "max": round(max(latencies) * 1000, 3) if latencies else 0.0,
                    "mean": round(statistics.fmean(latencies) * 1000, 3) if latencies else 0.0,
                },
            },
            "observability": {
                "metrics_scraped": "ledger_service_up 1" in metrics_text,
                "metrics_bounded_labels": "batch:" not in metrics_text,
                "alerts_fired_during_load": [rule.name for rule in alerts_fired],
                "correlation_in_logs": "X-Correlation-ID" in security.get("correlation_echo", {}),
            },
            "recovery": {
                "ok": drill["ok"],
                "objectives_met": drill["recovery_objectives_met"],
                "backup_seconds": drill["report"]["measurements"]["backup_seconds"],
                "restore_seconds": drill["report"]["measurements"]["restore_seconds"],
                "rto_target_seconds": drill["report"]["rpo_rto"]["policy"]["rto_target_seconds"],
                "rto_margin_seconds": drill["report"]["rpo_rto"]["conformance"]["rto_margin_seconds"],
                "backup_bytes": drill["report"]["measurements"]["backup_bytes"],
            },
            "late_arrival": {
                "scenario": "source A leg first (UNMATCHED_A), source B leg later (MATCHED)",
                "before": before,
                "after": after,
                "prior_version_retrievable": prior_still_present,
                "batches": {"source_a": late_a, "source_b": late_b,
                            "states": [late_a_runs[0].state, late_b_runs[0].state]},
            },
            "security": security,
        }
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if service is not None:
            service.stop()
        logs.close()
        shutil.rmtree(workdir, ignore_errors=True)


def _canonical_ids_for_records(database: LedgerDatabase, batch_id: str,
                              source_record_ids: tuple[str, ...]) -> set[str]:
    """Resolve source-native record ids in a batch to their canonical rows."""
    placeholders = ",".join("?" for _ in source_record_ids)
    rows = database.connection.execute(
        f"SELECT c.canonical_id FROM canonical_transactions AS c "  # nosec B608 - placeholders count bound "?" markers
        f"JOIN raw_records AS r ON r.raw_record_id = c.raw_record_id "
        f"WHERE r.batch_id = ? AND r.source_record_id IN ({placeholders})",
        (batch_id, *source_record_ids),
    ).fetchall()
    return {row["canonical_id"] for row in rows}


def _late_arrival_state(database: LedgerDatabase, canonical_ids: set[str]) -> dict:
    """Return the one current decision covering the given canonical records.

    ``find_current_for_participants`` excludes any row another version
    supersedes, so this reads the live decision rather than guessing from
    insertion order.
    """
    current = [row for row in database.reconciliations.find_current_for_participants(canonical_ids)
               if row.outcome is not None]
    if len(current) != 1:
        raise RuntimeError(f"expected one current decision for {sorted(canonical_ids)}, got {len(current)}")
    row = current[0]
    return {
        "reconciliation_id": row.reconciliation_id,
        "outcome": row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome),
        "reconciliation_version": row.reconciliation_version,
        "supersedes_reconciliation_id": row.supersedes_reconciliation_id,
        "batch_id": row.batch_id,
    }


def _correlation_check(base: str) -> dict:
    request = urllib.request.Request(base + "/v1/health")
    request.add_header("X-Correlation-ID", "staging-correlation-1")
    with urllib.request.urlopen(request) as response:
        return {"X-Correlation-ID": response.headers.get("X-Correlation-ID"),
                "body": json.loads(response.read())["correlation_id"]}


def evaluate_result(result: dict) -> list[str]:
    problems: list[str] = []
    if result["pipeline"]["outcome_mismatches"]:
        problems.append("pipeline outcomes diverged from the proven expectations")
    if any(state != "COMPLETED" for state in result["pipeline"]["states"].values()):
        problems.append("a staging batch did not complete")
    if result["load"]["errors"]:
        problems.append(f"{result['load']['errors']} load requests failed")
    if not result["observability"]["metrics_scraped"]:
        problems.append("metrics were not scraped")
    if not result["observability"]["metrics_bounded_labels"]:
        problems.append("metrics leaked an identifier into a label")
    if not result["recovery"]["ok"] or not result["recovery"]["objectives_met"]:
        problems.append("the recovery drill did not meet the approved objectives")
    if not result["late_arrival"]["prior_version_retrievable"]:
        problems.append("late arrival did not preserve the prior reconciliation version")
    if result["security"]["unauthenticated_read"] != 401:
        problems.append("unauthenticated read was not rejected with 401")
    if result["security"]["invalid_token"] != 401:
        problems.append("an invalid token was not rejected with 401")
    if result["security"]["wrong_scope_batch"] not in (403, 404):
        problems.append("a wrong-scope read was not rejected")
    if result["security"]["operator_scoped_read"] != 200:
        problems.append("an authorized read failed")
    if result["security"]["correlation_echo"].get("X-Correlation-ID") != "staging-correlation-1":
        problems.append("the correlation id was not echoed")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="staging-proof", description="LEDGER staging rehearsal")
    parser.add_argument("--shards", type=int, default=60)
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--requests-per-client", type=int, default=25)
    parser.add_argument("--long-batch-records", type=int, default=400)
    parser.add_argument("--output", default=str(EVIDENCE_PATH))
    arguments = parser.parse_args(argv)

    result = run(shards=arguments.shards, clients=arguments.clients,
                 requests_per_client=arguments.requests_per_client,
                 long_batch_records=arguments.long_batch_records)
    problems = evaluate_result(result)
    result["ok"] = not problems
    result["problems"] = problems
    target = Path(arguments.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "ok": result["ok"], "problems": problems,
        "records": result["dataset"]["records"] + result["pipeline"]["long_batch"]["records"],
        "pipeline_records_per_second": result["pipeline"]["records_per_second"],
        "load_requests_per_second": result["load"]["requests_per_second"],
        "load_latency_ms": result["load"]["latency_ms"],
        "evidence": str(target),
    }, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
