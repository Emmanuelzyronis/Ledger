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
- `GET /v1/health` and `GET /v1/ready` are the only unauthenticated operations.
  A degraded readiness probe returns `503` with the health **data** shape (not an
  error envelope) because it is a probe, not a business read.

## Read projections

Read endpoints return derived projections, never authoritative state. The
projection layer exposes stored JSON text columns under their base names
(`counters_json` → `counters`, `evidence_json` → `evidence`,
`metadata_json` → `metadata`) so clients never parse storage encodings.

`GET /v1/export` additionally redacts raw payloads and sensitive-looking fields
to `[REDACTED]`; exports are read-only and never authoritative.

## Known limitations

- **EMM-103:** resubmitting identical content into the *same* batch with a
  *different* idempotency key is not yet idempotent and currently surfaces as
  `500 internal_error`. The contract documents the supported behavior
  (resubmit with the original key). Tracked separately.
- Unversioned API paths are an alias, not a supported version.
- Write operations (source registration, batch creation, record ingestion) are
  authenticated and source-scoped but do not require a specific role in this
  cut; only discrepancy resolution requires `reconciliation_operator`.

## Verification

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_openapi_contract.py
PYTHONPATH=src python3 -m pytest -q
make check
```
