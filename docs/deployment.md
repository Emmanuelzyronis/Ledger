# LEDGER Deployment (Epic 7 / EMM-83)

How a release is built, promoted, deployed, rolled back, and operated. The
artifact contract is `scripts/release.py`; the runtime shapes are `Dockerfile`
and `deploy/`; the release process is `docs/release.md`.

## 1. Environments

| Environment | Purpose | Data | TLS | Secrets |
| --- | --- | --- | --- | --- |
| `development` | local iteration | disposable local SQLite | off | committed example tokens |
| `staging` | production-shaped rehearsal | representative fixtures, real volume | required | secret store |
| `production` | live reconciliation | authoritative volume | required | secret store |

All three run the **same** artifact and the same process model
(`Architecture` D-010, `docs/service.md`). Promotion changes configuration and
data, never code.

## 2. The deployable artifact

```sh
python3 scripts/release.py build --version 1.0.0 --output dist
python3 scripts/release.py verify  --artifact dist/ledger-1.0.0.tar.gz
```

`build` packages the tracked source tree into `dist/ledger-<version>.tar.gz`:

- deterministic tar contents (normalized owner, group, and mtime), plus
  `RELEASE-MANIFEST.json` inside the archive listing every file with its size
  and SHA-256;
- a `.sha256` companion file;
- `evidence/release-<version>.json` recording the git revision, artifact size,
  artifact digest, and the secret-scan result.

`build` **refuses to run** if any packaged file contains a secret-shaped value
(`LEDGER_TOKEN_SECRET=…`, `LEDGER_API_TOKENS=…`, a PEM private key, or an AWS
access key id). `verify` re-checks the checksum and re-runs the scan over the
archive contents.

## 3. Container

```sh
docker build --build-arg PYTHON_IMAGE=python:3.12.7-slim-bookworm --tag ledger:1.0.0 .
docker run --rm -p 127.0.0.1:8080:8080 \
  -e LEDGER_ENV=production \
  -e LEDGER_TOKEN_SECRET="$(openssl rand -hex 32)" \
  -v ledger-data:/var/lib/ledger \
  ledger:1.0.0
```

The image runs as uid 10001, has a read-only root filesystem in the Compose
stack, drops privileges, exposes `/v1/health` for the health check, and needs
exactly one writable volume: `/var/lib/ledger`. `LEDGER_DATABASE_PATH` defaults
to that volume. Pin the base image by digest before a production release.

## 4. Configuration and secrets

Configuration is non-secret environment values (`docs/service.md`). Secrets are
never baked into an artifact or committed:

- `deploy/env/<environment>.env.example` documents the required variables.
- Real values live in the platform secret store or `/etc/ledger/ledger.env`
  (mode `0640`, owner `root:ledger`) for the systemd path.
- `LEDGER_TOKEN_SECRET` must be at least 32 random bytes; rotating it
  invalidates outstanding bearer tokens.
- The at-rest encryption of the database volume is a **deployment obligation**
  (`docs/database-operations.md` §5) that this repository cannot verify; staging
  must assert it before production sign-off.

## 5. Promotion

1. **Build once.** `scripts/release.py build` produces the artifact; the same
   file is promoted. Never rebuild for staging or production.
2. **Scan.** `python3 scripts/scan.py --require-tools` must pass (bandit,
   pip-audit, trivy) and writes `evidence/security-scan.json`.
3. **Deploy to staging.**
   `docker compose --env-file deploy/env/staging.env -f deploy/docker-compose.yml up -d --build`
   then run the staging proof (`docs/staging.md`).
4. **Promote to production.** Run the go/no-go checklist
   (`docs/release-checklist.md`). Only then deploy the approved artifact.

## 6. Rollback

Rollback is a deployment of the previous artifact, not a partial revert:

```sh
python3 scripts/release.py build  --version 0.9.0 --output dist      # previous release
python3 scripts/release.py verify --artifact dist/ledger-0.9.0.tar.gz
python3 scripts/release.py rollback --artifact dist/ledger-0.9.0.tar.gz --target /opt/ledger --force
```

`rollback` verifies the artifact first, unpacks it beside the target, and moves
it into place atomically; the directory it replaces is preserved as
`<target>.pre-rollback-<timestamp>` rather than deleted. For containers, deploy
the previous image tag (`docker compose up -d --no-deps ledger` with
`LEDGER_IMAGE=ledger:0.9.0`).

**Database compatibility:** migrations are additive and idempotent, so a
rollback of the *service* does not roll back the schema. A migration that is not
backward compatible must be shipped as an expand/contract pair, or the rollback
must restore the pre-upgrade snapshot (`docs/database-operations.md` §3).

## 7. Operator batch progression (EMM-110)

The service is the data plane. Batches are advanced by the published operator
runner, which is the supported production path for `RECEIVED → COMPLETED`:

```sh
# List what is selectable
PYTHONPATH=src python3 -m ledger.pipeline list --database /var/lib/ledger/ledger.sqlite3

# Advance every pending batch (or one explicit batch id)
PYTHONPATH=src python3 -m ledger.pipeline process \
  --database /var/lib/ledger/ledger.sqlite3 --state VALIDATED
PYTHONPATH=src python3 -m ledger.pipeline process \
  --database /var/lib/ledger/ledger.sqlite3 --batch batch:abc
```

Exit codes: `0` success, `1` operator error (unknown batch, bad arguments),
`2` a stage failed. A failed run records a `processing_attempts` row in
`FAILED` and leaves the batch retryable (`FAILED`/`PARTIAL`) or untouched
(`RECEIVED`/`VALIDATING` when validation itself did not complete). Re-running is
idempotent: counters are recomputed from authoritative rows, and a `COMPLETED`
batch is never reopened. A late arrival arrives as a new batch; matching
re-evaluates and supersedes the affected decision under LA-1 while the earlier
batch summary stays historical.

Schedule it with `deploy/systemd/ledger-pipeline.service`, a job runner, or a
cron-style trigger — but the choice of *when* to process is an operator
decision, which is exactly why it is not an HTTP operation (EMM-110).

## 8. Backups

`deploy/systemd/ledger-backup.timer` runs a verified snapshot every 15 minutes
(the cadence that bounds the approved RPO in `Architecture.md` D-014) and writes
Prometheus textfile metrics so `LedgerBackupStale` fires when the cadence breaks.
The Compose stack provides the same service under the `backup` profile.

## 9. Verified local stack

`docker compose -f deploy/docker-compose.yml config` validates the stack
configuration. Bringing it up requires a container runtime, which is not
available in every development environment; the authoritative functional proof
remains `make check` plus the staged proof in `docs/staging.md`.

## 10. Honest limitations

- **No hosted environment is provisioned by this repository.** The Compose and
  systemd shapes are validated configurations, not a running deployment; staging
  and production bring-up is performed by the operator.
- **No CI provider is configured here.** `.github/workflows/ci.yml` is a
  ready-to-use pipeline definition; it has not been executed by a hosted runner,
  so its runtime is unverified.
- **Image digest pinning is a release step**, not an enforced invariant: the
  Dockerfile defaults to a tag so local builds work.
