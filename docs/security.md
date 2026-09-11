# LEDGER Security Baseline (EPIC 3 / EMM-79)

This is an explicit **baseline**, not an exhaustive hardening program. It records
the implemented controls, the threat model, the production assumptions, and the
known gaps. Deferred hardening is listed at the end.

## Controls implemented

### Identity and least privilege
- Bearer-token verification is a pluggable boundary (`ledger.security`):
  - `HmacTokenVerifier` — signed, expiring tokens (`v1.<payload>.<sig>`, HMAC-SHA256,
    constant-time comparison). Used when `LEDGER_TOKEN_SECRET` is configured.
    Deliberately not JWT; an OIDC/JWKS provider can replace it at the same boundary.
  - `StaticTokenVerifier` — development/local registry with constant-time
    comparison over every entry (no early exit to leak entry count/position).
- Principals carry `roles` and optional `source_ids`. The API layer enforces:
  - authentication required for every non-probe endpoint;
  - `source_ids` restrict batch/reconciliation/discrepancy/audit/report access
    (`_scope`, `_authorize_batch_filter`, `_filter_rows`);
  - `reconciliation_operator` role required for resolution; `reader` cannot resolve.
- `LEDGER_ENV=production` refuses to start without a configured identity source.

### Transport
- TLS is expected to terminate at the platform edge. `LEDGER_REQUIRE_TLS` defaults
  to `true` in production; non-probe requests over non-HTTPS fail with `tls_required`.
  `X-Forwarded-Proto` is honoured only as a proxy signal, never as authentication.
- Liveness/readiness probes are exempt from TLS so a platform can probe directly;
  they expose no business data and require no credentials.
- HSTS is emitted when TLS is required.

### Request limits
- Body size limit (`LEDGER_MAX_BODY_BYTES`) → HTTP 413.
- JSON depth limit (`LEDGER_MAX_JSON_DEPTH`) → HTTP 400 `payload_too_deep`.
- JSON parse failures → HTTP 400 `invalid_json`.
- Bodies on mutating methods must be `application/json` → HTTP 415.
- Unknown routes → HTTP 404; unsupported methods on known routes → 404/405 via dispatch.

### Abuse controls
- In-process fixed-window rate limiting (`LEDGER_RATE_LIMIT_PER_MINUTE`) keyed by
  client address → HTTP 429. Bounded key table with expiry pruning.
- CORS allowlist (`LEDGER_CORS_ORIGINS`): disallowed origins fail with 403;
  allowed origins receive `Access-Control-Allow-*` headers. Preflight `OPTIONS`
  returns 204 and requires no credentials.

### Response hardening
Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Cache-Control: no-store`, and a restrictive
`Content-Security-Policy`. HSTS is added when TLS is required.

### Redaction
- Telemetry uses the foundation redaction policy; token/authorization values are
  never placed in event attributes, so they never reach logs.
- Exports are derived projections and redact raw payload/description/secret/token
  fields; verified by tests.

## Threat model (baseline)

| Threat | Control | Evidence |
|---|---|---|
| Unauthenticated access to reconciliation data | Bearer auth required on all non-probe routes | `test_unauthenticated_api_request_is_rejected`, `api.source_isolation_*` proof checks |
| Forged/expired credentials | HMAC signature + expiry, constant-time compare | `test_hmac_token_tamper_rejection`, `test_hmac_token_expiry` |
| Credential timing oracle | Compare all registry entries / `hmac.compare_digest` | `test_static_verifier_*` |
| Cross-source data access | `source_ids` scoping on reads and batch filters | `test_source_isolation_and_roles` (product proof) |
| Unauthorized resolution | `reconciliation_operator` required; actor recorded per D-008 | `test_reader_role_cannot_resolve` |
| Request flooding / abuse | Fixed-window rate limit → 429 | `test_rate_limit_returns_429` |
| Oversized / deeply nested payloads (DoS, parser abuse) | Body byte limit + JSON depth limit | `test_json_depth_and_content_type_limits`, `test_oversized_body_is_rejected` |
| Content-type confusion | Mutating bodies must be `application/json` | `test_json_depth_and_content_type_limits` |
| Plaintext transport | `tls_required` when configured; HSTS | `test_tls_required_but_probe_paths_exempt` |
| Browser cross-origin abuse | CORS allowlist; disallowed origin → 403 | `test_origin_not_allowed_fails_closed` |
| Secret leakage via logs/exports | Redaction policy; no secrets in telemetry | `test_credentials_never_reach_telemetry`, `api.export_redacted` |
| Unauthorized state mutation | Only resolution mutates; domain authorization re-checked in `ResolutionService` | `ResolutionServiceTests` |

## Production assumptions (explicit)

1. TLS terminates at a trusted proxy/load balancer; the application is not
   internet-facing over plain HTTP.
2. `LEDGER_TOKEN_SECRET` (or an OIDC verifier replacing it) is supplied by the
   runtime environment or a secret manager; it is never committed.
3. `LEDGER_API_TOKENS` is for development/local use only.
4. A single process owns the SQLite file; horizontal scaling is out of scope for
   v1.0 (Architecture §33).
5. Rate limiting is per-process, so its effective limit multiplies with replicas.

## Known gaps (deferred, tracked)

These are deliberately **not** implemented in this baseline and must be closed
before any production release claim (EPIC 5–9):

- OIDC/JWKS provider integration, key rotation, and token revocation.
- Distributed rate limiting and per-route quotas.
- WAF/DDoS protection at the edge.
- SAST/dependency/container scanning (EPIC 7).
- Secret-manager integration and automated rotation (EPIC 5/7).
- mTLS or network policy between components.
- Audit-log shipping with tamper evidence (EPIC 6).

## Verification

```sh
python3 -m pytest -q tests/test_security.py     # 17 tests
python3 -m pytest -q                            # full regression
```
