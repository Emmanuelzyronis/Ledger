# LEDGER Service Boundary (EPIC 2 / EMM-78)

## Service strategy

LEDGER is exposed as a **single-process ASGI application** with **synchronous,
request-scoped execution**. The domain and API layers stay framework-independent
(`LedgerAPI.handle`); the service module owns only infrastructure concerns:
validated settings, database lifecycle, health/readiness, graceful drain, and
structured lifecycle telemetry.

Process model:

- One OS process, one authoritative SQLite database.
- No background workers, queues, or schedulers in the portfolio cut. Every
  authoritative write happens inside the HTTP request that triggers it, so a
  failed request leaves no partial business state (the domain/persistence
  transactions already guarantee atomicity).
- The HTTP boundary may use worker threads; the shared SQLite connection is
  serialized by a re-entrant lock (`_SynchronizedConnection`), so concurrent
  requests cannot interleave statements on one connection.
- Restart is safe: completed authoritative work is never repeated incorrectly,
  and a reopened database reproduces identical state.

## Configuration

All configuration is non-secret environment values with safe defaults
(`ledger.service.ServiceSettings`). Invalid values fail startup explicitly.

| Variable | Default | Meaning |
|---|---|---|
| `LEDGER_ENV` | `development` | `development`, `test`, or `production` |
| `LEDGER_LOG_LEVEL` | `INFO` | supported Python log level |
| `LEDGER_TELEMETRY_ENABLED` | `true` | enable structured telemetry |
| `LEDGER_HOST` | `127.0.0.1` | bind host |
| `LEDGER_PORT` | `8080` | bind port (1–65535) |
| `LEDGER_DATABASE_PATH` | `ledger.sqlite3` | path to the authoritative SQLite database |
| `LEDGER_MAX_BODY_BYTES` | `1048576` | request body limit (larger bodies get HTTP 413) |
| `LEDGER_DRAIN_TIMEOUT_SECONDS` | `10` | how long shutdown waits for in-flight requests |
| `LEDGER_API_TOKENS` | *(empty)* | baseline opaque bearer tokens, `token:role[:source|source]` |

Secrets are never hardcoded and are supplied by the runtime environment or a
secret manager (see `.env.example`). Tokens are never logged.

## Running

Dependency-free local runner (stdlib HTTP server, SIGINT/SIGTERM graceful stop):

```sh
PYTHONPATH=src LEDGER_DATABASE_PATH=ledger.sqlite3 python3 -m ledger
# or
make run
```

Production-shaped ASGI path (any ASGI server):

```sh
uvicorn ledger.service:create_app --factory --host 127.0.0.1 --port 8080
```

The ASGI application is deployment-neutral: it can be served by uvicorn,
hypercorn, or any ASGI-compatible server without changing the domain code.

## Health and readiness

- `GET /health` — **liveness**: the process is responsive. Unauthenticated.
- `GET /ready` — **readiness**: application *and* authoritative database are
  available. Unauthenticated. Returns HTTP 503 with
  `{"database": "unavailable"}` when the database cannot be reached.

All other endpoints require bearer authentication through the existing
`LedgerAPI` boundary.

## Graceful shutdown and restart

`LedgerService.stop()` stops accepting new work, waits up to
`LEDGER_DRAIN_TIMEOUT_SECONDS` for in-flight requests to finish, then closes the
database. A drain timeout is recorded as `ledger.service.drain_timeout`
telemetry rather than silently dropping work. Startup/shutdown emit
`ledger.service.started` / `ledger.service.stopped` structured events.

## Verification

```sh
python3 -m pytest -q tests/test_service.py     # 14 service tests
python3 -m pytest -q                            # full regression
python3 -m compileall -q src tests benchmarks product_proof
git diff --check
```

Covered: settings validation, idempotent start, configuration-bound serving,
public health/readiness, database-unavailable readiness failure, authentication
rejection, in-flight drain on shutdown, lifecycle telemetry redaction, ASGI
lifespan + HTTP translation, JSON/oversized-body rejection, HTTP round-trip over
a real socket, and file-backed restart persistence.

## Limitations (tracked, not silent)

- The baseline token verifier is an exact-match opaque-token registry, not a
  production identity provider; constant-time comparison, token rotation, TLS,
  rate limiting, and security headers are EPIC 3 (EMM-79) scope.
- No connection pooling or horizontal scaling: the architecture is a modular
  monolith over one relational authority for v1.0 (Architecture §33).
