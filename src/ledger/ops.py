"""Operator-facing database operations: migrations, backup, restore, and drills.

Usage::

    PYTHONPATH=src python3 -m ledger.ops migrate   --database ledger.sqlite3 [--status]
    PYTHONPATH=src python3 -m ledger.ops integrity --database ledger.sqlite3
    PYTHONPATH=src python3 -m ledger.ops backup    --database ledger.sqlite3 --output backup.sqlite3
    PYTHONPATH=src python3 -m ledger.ops verify    --backup backup.sqlite3
    PYTHONPATH=src python3 -m ledger.ops restore   --backup backup.sqlite3 --database ledger.sqlite3 --force
    PYTHONPATH=src python3 -m ledger.ops drill     --database ledger.sqlite3 --workdir /tmp/ledger-drill
    PYTHONPATH=src python3 -m ledger.ops retention

Every subcommand is read-only unless it is ``migrate``, ``backup``, ``restore``,
or ``drill``. Nothing here deletes authoritative rows; see ``ledger.retention``.

Numerical RPO/RTO targets are **not** set here. Architecture D-009 defers
numerical SLOs, so the drill measures what recovery costs and reports the
numbers; approving targets is an architecture-owner decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .migrations import MigrationRunner
from .persistence import LedgerDatabase
from .retention import AUTHORITATIVE_TABLES, describe as describe_retention, open_readonly

SCHEMA_VERSION = 1

# Tables whose contents define the authoritative state a restore must preserve.
STATE_TABLES = (
    "sources",
    "batches",
    "processing_attempts",
    "raw_records",
    "canonical_transactions",
    "match_candidates",
    "reconciliations",
    "discrepancies",
    "resolutions",
    "audit_events",
)


class OpsError(RuntimeError):
    """An operator command refused to proceed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _digest(connection: sqlite3.Connection, table: str) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1"):
        digest.update(json.dumps([str(value) for value in tuple(row)]).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _immutability_enforced(path: str | Path) -> bool:
    """Prove the append-only triggers survived: an UPDATE on audit events must fail."""
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("SELECT event_id FROM audit_events ORDER BY 1 LIMIT 1").fetchone()
        if row is None:
            return True
        try:
            connection.execute(
                "UPDATE audit_events SET actor = actor WHERE event_id = ?", (row[0],)
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return True
        connection.rollback()
        return False
    finally:
        connection.close()


def snapshot(path: str | Path) -> dict[str, Any]:
    """Counts and content digests for every authoritative table, plus integrity."""
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        tables: dict[str, Any] = {}
        for table in STATE_TABLES:
            if not _table_exists(connection, table):
                tables[table] = {"rows": None, "digest": None, "present": False}
                continue
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            tables[table] = {"rows": count, "digest": _digest(connection, table), "present": True}
        return {
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "immutability_enforced": _immutability_enforced(path),
            "tables": tables,
        }
    finally:
        connection.close()


def verify(path: str | Path) -> dict[str, Any]:
    """Read-only verification of a database or backup file."""
    target = Path(path)
    if not target.exists():
        return {"ok": False, "path": str(target), "error": "file does not exist"}
    try:
        connection = open_readonly(target)
    except sqlite3.Error as exc:
        return {"ok": False, "path": str(target), "error": str(exc)}
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        missing = sorted(table for table in AUTHORITATIVE_TABLES if not _table_exists(connection, table))
        history: list[str] = []
        if _table_exists(connection, "schema_migrations"):
            history = [row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version")]
        return {
            "ok": integrity == "ok" and not foreign and not missing and bool(history),
            "path": str(target),
            "integrity": integrity,
            "foreign_key_violations": len(foreign),
            "missing_tables": missing,
            "migration_history": history,
        }
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "path": str(target), "error": str(exc)}
    finally:
        connection.close()


def migrate(database_path: str, *, status_only: bool = False) -> dict[str, Any]:
    database = LedgerDatabase(database_path)
    try:
        runner = MigrationRunner(database)
        applied = [] if status_only else [migration.version for migration in runner.apply()]
        return {"database": database_path, "applied": applied, "history": runner.describe()}
    finally:
        database.close()


def backup(database_path: str, output_path: str) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists():
        raise OpsError(f"{output} already exists; refusing to overwrite a backup")
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("VACUUM INTO ?", (str(output),))
    finally:
        connection.close()
    duration = time.perf_counter() - started
    report = verify(output)
    if not report["ok"]:
        output.unlink(missing_ok=True)
        raise OpsError(f"backup at {output} failed verification: {report}")
    return {
        "database": database_path,
        "output": str(output),
        "bytes": output.stat().st_size,
        "duration_seconds": round(duration, 4),
        "verification": report,
    }


def restore(backup_path: str, database_path: str, *, force: bool = False) -> dict[str, Any]:
    report = verify(backup_path)
    if not report["ok"]:
        raise OpsError(f"backup at {backup_path} failed verification; refusing to restore")
    target = Path(database_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    preserved: Path | None = None
    if target.exists():
        if not force:
            raise OpsError(f"{target} exists; pass --force to replace it")
        preserved = target.with_name(f"{target.name}.pre-restore-{_slug()}")
        os.replace(target, preserved)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{target}{suffix}")
            if sidecar.exists():
                os.replace(sidecar, Path(f"{preserved}{suffix}"))
    temporary = target.with_name(f"{target.name}.restore-tmp")
    started = time.perf_counter()
    shutil.copyfile(backup_path, temporary)
    with open(temporary, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    duration = time.perf_counter() - started
    restored = verify(target)
    if not restored["ok"]:
        raise OpsError(f"restored database at {target} failed verification: {restored}")
    return {
        "backup": backup_path,
        "database": str(target),
        "preserved": str(preserved) if preserved else None,
        "duration_seconds": round(duration, 4),
        "verification": restored,
    }


def drill(database_path: str, workdir: str, *, evidence_path: str | None = None) -> dict[str, Any]:
    """Timed backup/restore/recovery drill with a corruption-detection proof."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    before = snapshot(database_path)

    backup_report = backup(database_path, str(work / "ledger-backup.sqlite3"))
    restored_report = restore(
        backup_report["output"], str(work / "ledger-restored.sqlite3"), force=False
    )
    after = snapshot(restored_report["database"])

    corrupt_path = work / "ledger-corrupt.sqlite3"
    shutil.copyfile(backup_report["output"], corrupt_path)
    with open(corrupt_path, "r+b") as handle:
        handle.seek(0)
        handle.write(b"\x00" * 16)
    corruption = verify(corrupt_path)
    corruption_refused = False
    try:
        restore(str(corrupt_path), str(work / "should-not-exist.sqlite3"))
    except OpsError:
        corruption_refused = True

    preserved = all(
        before["tables"].get(table) == after["tables"].get(table) for table in STATE_TABLES
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "database": database_path,
        "environment": {
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
        },
        "method": "VACUUM INTO snapshot -> read-only verify -> restore copy -> re-verify",
        "measurements": {
            "backup_seconds": backup_report["duration_seconds"],
            "restore_seconds": restored_report["duration_seconds"],
            "drill_seconds": round(time.perf_counter() - started, 4),
            "backup_bytes": backup_report["bytes"],
        },
        "results": {
            "authoritative_state_preserved": preserved,
            "immutability_enforced_after_restore": after["immutability_enforced"],
            "backup_verification": backup_report["verification"],
            "restore_verification": restored_report["verification"],
            "corruption_detected": not corruption["ok"],
            "corruption_error": corruption.get("error") or corruption.get("integrity"),
            "corrupt_backup_refused": corruption_refused,
            "tables_before": {k: v["rows"] for k, v in before["tables"].items()},
        },
        "rpo_rto": {
            "status": "targets_unapproved",
            "note": "Architecture D-009 defers numerical SLOs; approving RPO/RTO is an architecture-owner decision.",
            "observed": {
                "backup_seconds": backup_report["duration_seconds"],
                "restore_seconds": restored_report["duration_seconds"],
            },
        },
        "retention": describe_retention(),
    }
    state = {
        "ok": preserved
        and after["immutability_enforced"]
        and not corruption["ok"]
        and corruption_refused,
        "report": report,
    }
    if evidence_path:
        target = Path(evidence_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        state["evidence"] = str(target)
    return state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger.ops", description="LEDGER database operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate", help="apply versioned schema migrations")
    migrate_parser.add_argument("--database", required=True)
    migrate_parser.add_argument("--status", action="store_true", help="report history without applying")

    integrity_parser = subparsers.add_parser("integrity", help="verify a database read-only")
    integrity_parser.add_argument("--database", required=True)

    backup_parser = subparsers.add_parser("backup", help="write a verified consistent snapshot")
    backup_parser.add_argument("--database", required=True)
    backup_parser.add_argument("--output", required=True)

    verify_parser = subparsers.add_parser("verify", help="verify a backup read-only")
    verify_parser.add_argument("--backup", required=True)

    restore_parser = subparsers.add_parser("restore", help="restore a verified backup")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--database", required=True)
    restore_parser.add_argument("--force", action="store_true", help="replace an existing database")

    drill_parser = subparsers.add_parser("drill", help="run a timed backup/restore/recovery drill")
    drill_parser.add_argument("--database", required=True)
    drill_parser.add_argument("--workdir", required=True)
    drill_parser.add_argument("--evidence", default=None)

    subparsers.add_parser("retention", help="print the retention policy")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        if arguments.command == "migrate":
            result = migrate(arguments.database, status_only=arguments.status)
        elif arguments.command == "integrity":
            result = verify(arguments.database)
        elif arguments.command == "backup":
            result = backup(arguments.database, arguments.output)
        elif arguments.command == "verify":
            result = verify(arguments.backup)
        elif arguments.command == "restore":
            result = restore(arguments.backup, arguments.database, force=arguments.force)
        elif arguments.command == "drill":
            result = drill(arguments.database, arguments.workdir, evidence_path=arguments.evidence)
        else:
            result = describe_retention()
    except OpsError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not isinstance(result, dict) or result.get("ok", True) else 1


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
