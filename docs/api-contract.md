# LEDGER API Contract (EPIC 4 / EMM-80)

## Artifact

The published contract is a machine-readable OpenAPI 3.1 document:

- `docs/openapi/ledger.v1.json` — the source of truth for the HTTP interface.

The document is written by hand and guarded by `tests/test_openapi_contract.py`.
The tests load the artifact, resolve every `$ref`, check coverage against the
operations implemented in `src/ledger/api.py` / `src/ledger/service.py`, validate
the document's own request/response examples, and drive the **real**
`LedgerService` through every documented operation and error code, validating
each response against the published schema.

## Versioning policy

- The published contract is **`/v1`**. It is the only version served.
- A version-looking prefix other than `v1` (for example `/v2/reports`) is
  rejected with `404` / `unsupported_api_version`; it is never answered by `v1`.
- Backward-compatible changes (new endpoints, new optional request fields, new
  response fields, new members of open enum sets) may be made in place inside
  `/v1`, and `info.version` is incremented.
- Breaking changes (removing/renaming a field, changing a type or meaning,
  tightening validation, changing the status code for an existing condition)
  require a new `/v2` prefix.
- Unversioned paths (for example `/reports`) still resolve as a compatibility
  alias for `/v1` because the framework-independent `LedgerAPI` is also used
  in-process and in tests. **The alias is not part of the contract**; the
  frontend and any other integration must call `/v1`.

## Status and error contract

- Success: `200` with `{"data": ..., "correlation_id": "..."}`.
- Error: `{"error": {"code": "...", "message": "..."}, "correlation_id": "..."}`.
  `code` is stable and machine-readable; `message` is not stable.
- The complete set of codes served by `/v1` is enumerated in the document's
  `x-ledger-error-codes` extension and in `ErrorDetail.code`.
- `X-Correlation-ID` is echoed on both success and error responses; the service
  also propagates it between the service and API layers.
- `GET /v1/health`, `GET /v1/ready`, and `GET /v1/metrics` are the only
  unauthenticated operations. A degraded readiness probe returns `503` with the
  health **data** shape (not an error envelope) because it is a probe, not a
  business read. `/v1/metrics` returns Prometheus text exposition, not JSON, and
  is an observability probe rather than a versioned business operation
  (`docs/observability.md`); it carries bounded labels only.

## Read projections

Read endpoints return derived projections, never authoritative state. The
projection layer exposes stored JSON text columns under their base names
(`counters_json` → `counters`, `evidence_json` → `evidence`,
`metadata_json` → `metadata`) so clients never parse storage encodings.

`GET /v1/export` additionally redacts raw payloads and sensitive-looking fields
to `[REDACTED]`; exports are read-only and never authoritative.

## Known limitations

- Resubmitting identical content into the *same* batch is idempotent for any
  idempotency key: it returns the original `raw_record_id` with
  `duplicate_submission: true` and writes no new raw record, counter, or audit
  event. Identical content in a *different* batch links the same raw record to
  that batch without duplicating it.
- Unversioned API paths are an alias, not a supported version.
- Write operations (source registration, batch creation, record ingestion) are
  authenticated and source-scoped but do not require a specific role in this
  cut; only discrepancy resolution requires `reconciliation_operator`.

## Path parameters and source scoping

- Path segments are percent-decoded after the route is split, so an identifier
  containing a reserved character (every LEDGER id contains `:`) works whether
  it is sent raw or percent-encoded. An encoded `/` can never change the route.
- A principal configured with `source_ids` sees only rows whose batch belongs to
  an allowed source. This covers batch and reconciliation reads, the
  discrepancy list and detail, and the audit trail for `batch`, `record`,
  `reconciliation`, `discrepancy`, and `resolution` subjects; out-of-scope
  subjects return `403 forbidden`.

Both behaviors were fixed during the EMM-105 dashboard pass and are guarded by
`ScopedReadTests` in `tests/test_openapi_contract.py`.

## Verification

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_openapi_contract.py
PYTHONPATH=src python3 -m pytest -q
make check
```
