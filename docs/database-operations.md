# LEDGER Database Operations (Epic 5 / EMM-81)

Authoritative LEDGER state lives in one SQLite database. This document is the
operator runbook for schema migrations, backup, restore, retention, encryption,
least privilege, and recovery drills. Code lives in `src/ledger/migrations.py`,
`src/ledger/retention.py`, and `src/ledger/ops.py`; tests are in
`tests/test_database_operations.py`.

## 1. Database boundary

**Decision: retain SQLite as the single authoritative store for v1.0.** This
follows `Architecture.md` (§ "single authoritative data store", persistence
layer) rather than choosing a new database. Moving to a server database is an
architecture change and needs architecture-owner approval; it is not a routine
operations decision.

Explicit operational limits that follow from that choice:

- One writer process per database file. The service (`Architecture` D-010) is a
  single-process ASGI application with synchronous, request-scoped writes, so
  there is no writer contention to arbitrate.
- The database file is local storage. It is not shared over a network
  filesystem; SQLite locking is not reliable there.
- Durability depends on the volume: use a persistent disk, not container-local
  ephemeral storage, and enable the storage layer's encryption.
- Writer transactions use `BEGIN IMMEDIATE`; readers see committed state only.
- The journal is **WAL with `synchronous=FULL`** (Epic 8 / EMM-84). Durability
  is unchanged — a committed transaction survives power loss — but committed
  pages may live only in the `-wal` sidecar until a checkpoint. A snapshot must
  therefore go through `VACUUM INTO` (as `ledger.ops backup` does), the SQLite
  backup API, or a stopped-service file copy. Never copy the database file
  alone while a writer is running.
- Capacity is bounded by the volume. A snapshot is a full, compact copy of the
  database, so the size of the largest table set (`raw_records`,
  `audit_events`) drives backup cost.

## 2. Migrations

Schema history is explicit and versioned.

- `schema_migrations` records `version`, `name`, `applied_at`, and whether the
  row is the baseline.
- `0001` is the **baseline**: the Layer 3 schema created idempotently by
  `LedgerDatabase._create_schema`. A database that predates this module is
  *adopted* — the baseline is recorded against the schema already present
  instead of being re-executed.
- Every later migration is numbered, ordered, additive, and idempotent. Each
  runs in one transaction; a failure leaves both the schema and the history
  unchanged.
- `LedgerDatabase()` applies pending migrations on open, so starting the service
  upgrades the schema. `apply()` is idempotent.

```sh
# Report history without applying anything
PYTHONPATH=src python3 -m ledger.ops migrate --database ledger.sqlite3 --status

# Apply pending migrations (the service also does this on start)
PYTHONPATH=src python3 -m ledger.ops migrate --database ledger.sqlite3
```

Current set: `0001 initial_schema` (baseline), `0002 operational_lookup_indexes`
(indexes for audit-by-entity, discrepancies-by-reconciliation,
reconciliations-by-batch, raw-records-by-batch, and validation-by-batch reads).

## 3. Backup and restore

```sh
# Verified snapshot (refuses to overwrite an existing backup file)
PYTHONPATH=src python3 -m ledger.ops backup --database ledger.sqlite3 --output ledger-$(date -u +%Y%m%dT%H%M%SZ).sqlite3

# Verify a backup without restoring it
PYTHONPATH=src python3 -m ledger.ops verify --backup ledger-20260101T000000Z.sqlite3

# Restore (refuses without --force; the previous file is kept as
# <name>.pre-restore-<timestamp>)
PYTHONPATH=src python3 -m ledger.ops restore --backup backup.sqlite3 --database ledger.sqlite3 --force
```

Mechanics and safety properties:

- Backups use `VACUUM INTO`, which produces a consistent, compact snapshot from a
  live database without stopping the service.
- Every backup is verified before it is kept: `PRAGMA integrity_check`,
  `PRAGMA foreign_key_check`, presence of every authoritative table, and a
  non-empty migration history. A backup that fails is deleted.
- Restore verifies the backup **first** and refuses to restore an unverified
  file. The copy is written to a temporary name, fsynced, and moved into place
  atomically, so a failed restore cannot leave a half-written database.
- A replaced database is preserved rather than deleted, and its `-wal`/`-shm`
  sidecars move with it.
- Restoring does not "fix" corruption: a corrupt backup is refused.

## 4. Retention

Retention is **fail-closed**. `ledger.retention` classifies every table, and
`assert_prunable(table)` raises for anything authoritative or unclassified.

In v1.0 the prunable set is **empty**.

- Raw evidence, canonical versions, reconciliation versions, discrepancies,
  resolutions, and audit events are retained indefinitely.
- Match candidates are rebuildable in principle, but matching evidence stores
  candidate ids, so deleting them would make retained evidence unreadable.
  They are therefore retained as well.

```sh
PYTHONPATH=src python3 -m ledger.ops retention
```

Retention of *derived* artifacts — export files, application logs, telemetry —
belongs to the deployment and the observability stack, not to this module. Those
artifacts are never authoritative.

## 5. Encryption and secrets

- **In transit:** the service refuses production traffic without TLS
  (`LEDGER_REQUIRE_TLS`; see `docs/service.md` and `docs/security.md`).
- **At rest:** the database file and its backups must be on an encrypted volume
  or encrypted object store. LEDGER does not implement file-level encryption and
  deliberately does not add a dependency to do so; this is a deployment control
  that the runbook records as an obligation, not an implemented feature.
- **Secrets:** tokens and keys come from the environment or a secret manager via
  `ledger.config.load_secret`. No credential is written into the database or
  into source.

**Limitation:** because at-rest encryption is delegated to the storage layer,
this repository cannot verify it. Staging verification must assert the volume is
encrypted before production sign-off.

## 6. Least privilege

- Operators verify and report with read-only connections
  (`ledger.retention.open_readonly`, `mode=ro` plus `PRAGMA query_only`), so a
  mistake cannot write.
- The service account owns read/write on the database file and its directory.
  Operator tooling needs read access to the file and write access only to the
  backup destination.
- No component runs as `root`.

## 7. RPO/RTO

**Approved for v1.0 in `Architecture.md` D-014** (Epic 5 / EMM-108). This is a
data-recovery policy; the numerical *performance* SLOs remain deferred under
D-009.

| Objective | Target | Enforced by |
| --------- | ------ | ----------- |
| RPO       | ≤ 15 min | verified full snapshot every 15 min (24 h local retention) + daily offsite (30 d) |
| RTO       | ≤ 30 min | detection → operator action → restore → verify → service start |

A snapshot that fails verification is not a recovery point; the previous verified
snapshot is. Backup failures must alert (Epic 6) so the cadence that bounds the
RPO is never silently broken.

The drill in §8 measures the mechanical recovery path and reports it against the
approved targets: `rpo_rto.status = "approved"`, the policy it compared against,
and `conformance.rto_seconds_within_target` with the margin. On the
representative fixture database (17 raw records, 16 canonical transactions, 13
reconciliations, 5 discrepancies, 75 audit events, ~308 KiB) backup and restore
together take well under a second, so the measured margin against the 30 minute
RTO is large. These are small-dataset numbers and must not be extrapolated to
production capacity; the 15 minute RPO is bounded by the backup cadence, not by
the drill's runtime.

**SQLite boundary:** the single-writer store in §1 is accepted for these targets
(D-014). No database-boundary change is required. Reassess if a later decision
reverses the single-writer or backup strategy.

## 8. Drills and evidence

```sh
PYTHONPATH=src python3 product_proof/seed_database.py /tmp/ledger-ops-drill.sqlite3
PYTHONPATH=src python3 -m ledger.ops drill \
  --database /tmp/ledger-ops-drill.sqlite3 \
  --workdir /tmp/ledger-ops-work \
  --evidence evidence/database-operations.json
```

The drill:

1. snapshots every authoritative table (row counts and content digests);
2. takes a verified backup and records its size and duration;
3. restores it into a new database and re-verifies integrity, foreign keys,
   immutability triggers, and that every authoritative table is byte-identical
   to the original;
4. corrupts a copy of the backup, proves `verify` detects it, and proves
   `restore` refuses it;
5. writes `evidence/database-operations.json`.

`tests/test_database_operations.py` runs the same properties as tests: 13 cases
covering migration history and adoption, idempotent apply, backup verification
and overwrite refusal, restore with preserved audit lineage and pre-restore copy,
corruption detection and refusal, the drill report, read-only enforcement, and
the retention guard.

## 9. Open items (not silently accepted)

- **Selecting a production database** (if SQLite's limits in §1 are
  unacceptable) requires an architecture change.
- **At-rest encryption is delegated** to the storage layer and cannot be verified
  from this repository; staging must assert it.
- **Backup scheduling, offsite replication, backup-failure alerting, and staging
  restore rehearsals must be implemented and proven** by the deployment and
  observability epics (6-8); D-014 approves the targets but those controls are not
  yet built. Until then the approved RPO is a policy, not an enforced guarantee.
