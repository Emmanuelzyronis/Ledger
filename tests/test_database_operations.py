"""Epic 5 (EMM-81) database operations: migrations, backup/restore, drills, retention.

The tests drive the real ``LedgerDatabase`` and the real operator commands over a
representative fixture database, and assert the invariants the epic must
preserve: authoritative state and audit lineage survive backup/restore, the
append-only triggers still reject mutation afterwards, corruption is detected
and never restored, and nothing authoritative is ever pruned.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ledger import ops  # noqa: E402
from ledger.ingestion import RawIngestion  # noqa: E402
from ledger.migrations import BASELINE_VERSION, MIGRATIONS, MigrationRunner  # noqa: E402
from ledger.persistence import LedgerDatabase  # noqa: E402
from ledger.retention import (  # noqa: E402
    AUTHORITATIVE_TABLES,
    RetentionError,
    assert_prunable,
    describe,
    open_readonly,
)
from product_proof import dataset  # noqa: E402
from product_proof.pipeline import register_sources, run_standard_pipeline, seed_records  # noqa: E402


def seed(database_path: str) -> None:
    """Populate a real database with the Layer 15 portfolio fixtures."""
    database = LedgerDatabase(database_path)
    try:
        ingestion = RawIngestion(database)
        register_sources(ingestion)
        batch_a, _ = seed_records(
            database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
            batch_id="ops-batch-a", external_batch_id="ops-ext-a", idempotency_prefix="ops-a")
        batch_b, _ = seed_records(
            database, "source-b", "source_b.v1", dataset.PORTFOLIO_B,
            batch_id="ops-batch-b", external_batch_id="ops-ext-b", idempotency_prefix="ops-b")
        run_standard_pipeline(database, [batch_a, batch_b], reconcile_invalid=True)
    finally:
        database.close()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="ledger-migrations-")
        self.path = str(Path(self.directory) / "ledger.sqlite3")
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def test_fresh_database_records_baseline_then_every_migration(self):
        database = LedgerDatabase(self.path)
        self.addCleanup(database.close)
        history = database.migrations.history()
        self.assertEqual(history[0].version, BASELINE_VERSION)
        self.assertTrue(history[0].baseline)
        self.assertEqual([record.version for record in history],
                         [BASELINE_VERSION] + [migration.version for migration in MIGRATIONS])
        self.assertEqual(database.migrations.pending(), [])

    def test_apply_is_idempotent_and_returns_only_new_work(self):
        database = LedgerDatabase(self.path)
        self.addCleanup(database.close)
        self.assertEqual(database.migrations.apply(), [])
        before = database.migrations.history()
        self.assertEqual(database.migrations.apply(), [])
        self.assertEqual(database.migrations.history(), before)

    def test_a_pre_migration_database_is_adopted_not_rebuilt(self):
        database = LedgerDatabase(self.path)
        ingestion = RawIngestion(database)
        register_sources(ingestion)
        seed_records(database, "source-a", "source_a.v1", dataset.PORTFOLIO_A,
                     batch_id="adopt-a", external_batch_id="adopt-ext-a",
                     idempotency_prefix="adopt-a")
        database.connection.execute("DROP TABLE schema_migrations")
        database.connection.commit()
        database.close()

        adopted = LedgerDatabase(self.path)
        self.addCleanup(adopted.close)
        versions = [record.version for record in adopted.migrations.history()]
        self.assertEqual(versions, [BASELINE_VERSION] + [m.version for m in MIGRATIONS])
        # Adoption preserves the data that was already there.
        self.assertEqual(adopted.batches.get("adopt-a").batch_id, "adopt-a")

    def test_status_only_reports_without_applying(self):
        result = ops.migrate(self.path, status_only=True)
        self.assertEqual(result["applied"], [])
        self.assertTrue(all(row["state"] == "applied" for row in result["history"]))

    def test_describe_reports_every_known_migration(self):
        database = LedgerDatabase(self.path)
        self.addCleanup(database.close)
        rows = database.migrations.describe()
        self.assertEqual(len(rows), 1 + len(MIGRATIONS))
        self.assertTrue(all(row["state"] == "applied" for row in rows))
        self.assertTrue(rows[0]["baseline"])


class BackupRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp(prefix="ledger-ops-")
        cls.database = str(Path(cls.directory) / "ledger.sqlite3")
        seed(cls.database)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_backup_is_verified_and_does_not_overwrite(self):
        output = str(Path(self.directory) / "backup-1.sqlite3")
        report = ops.backup(self.database, output)
        self.assertTrue(report["verification"]["ok"])
        self.assertGreater(report["bytes"], 0)
        with self.assertRaises(ops.OpsError):
            ops.backup(self.database, output)

    def test_restore_preserves_authoritative_state_and_audit_lineage(self):
        backup_path = str(Path(self.directory) / "backup-restore.sqlite3")
        ops.backup(self.database, backup_path)
        restored_path = str(Path(self.directory) / "restored.sqlite3")

        before = ops.snapshot(self.database)
        ops.restore(backup_path, restored_path)
        after = ops.snapshot(restored_path)

        for table in ops.STATE_TABLES:
            self.assertEqual(before["tables"][table], after["tables"][table], table)
        self.assertEqual(after["integrity"], "ok")
        self.assertEqual(after["foreign_key_violations"], 0)
        self.assertTrue(after["immutability_enforced"], "append-only triggers must survive restore")

        # Immutable history is still immutable after the round trip.
        connection = sqlite3.connect(restored_path)
        try:
            event_id = connection.execute("SELECT event_id FROM audit_events LIMIT 1").fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM audit_events WHERE event_id = ?", (event_id,))
        finally:
            connection.close()

    def test_restore_requires_force_and_preserves_the_previous_database(self):
        backup_path = str(Path(self.directory) / "backup-force.sqlite3")
        ops.backup(self.database, backup_path)
        target = str(Path(self.directory) / "existing.sqlite3")
        shutil.copyfile(self.database, target)

        with self.assertRaises(ops.OpsError):
            ops.restore(backup_path, target)
        report = ops.restore(backup_path, target, force=True)
        self.assertIsNotNone(report["preserved"])
        self.assertTrue(Path(report["preserved"]).exists())
        self.assertTrue(report["verification"]["ok"])

    def test_corruption_is_detected_and_never_restored(self):
        backup_path = str(Path(self.directory) / "backup-corrupt.sqlite3")
        ops.backup(self.database, backup_path)
        corrupt = Path(self.directory) / "corrupt.sqlite3"
        shutil.copyfile(backup_path, corrupt)
        with open(corrupt, "r+b") as handle:
            handle.seek(0)
            handle.write(b"\x00" * 16)

        report = ops.verify(corrupt)
        self.assertFalse(report["ok"])
        with self.assertRaises(ops.OpsError):
            ops.restore(str(corrupt), str(Path(self.directory) / "never.sqlite3"))
        self.assertFalse((Path(self.directory) / "never.sqlite3").exists())

    def test_drill_reports_measurements_and_a_positive_result(self):
        state = ops.drill(self.database, str(Path(self.directory) / "drill"))
        self.assertTrue(state["ok"], state["report"]["results"])
        report = state["report"]
        self.assertTrue(report["results"]["authoritative_state_preserved"])
        self.assertTrue(report["results"]["corruption_detected"])
        self.assertTrue(report["results"]["corrupt_backup_refused"])
        self.assertGreater(report["measurements"]["backup_bytes"], 0)
        self.assertEqual(report["rpo_rto"]["status"], "targets_unapproved")


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp(prefix="ledger-controls-")
        cls.database = str(Path(cls.directory) / "ledger.sqlite3")
        seed(cls.database)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_read_only_connection_rejects_writes(self):
        connection = open_readonly(self.database)
        self.addCleanup(connection.close)
        self.assertGreater(connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("DELETE FROM batches")

    def test_no_authoritative_table_is_prunable(self):
        policy = describe()
        self.assertEqual(policy["prunable"], [])
        self.assertEqual(set(policy["retained"]), set(AUTHORITATIVE_TABLES))
        for table in AUTHORITATIVE_TABLES:
            with self.assertRaises(RetentionError):
                assert_prunable(table)

    def test_unknown_table_is_not_prunable(self):
        with self.assertRaises(RetentionError):
            assert_prunable("not_a_ledger_table")


if __name__ == "__main__":
    unittest.main()
