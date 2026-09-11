"""EPIC 3 baseline security-boundary tests (identity, limits, headers, transport)."""

from __future__ import annotations

import json
import unittest

from ledger.config import ConfigError, Settings
from ledger.observability import InMemoryTelemetrySink
from ledger.security import (
    HmacTokenVerifier,
    Principal,
    RateLimiter,
    SecurityPolicy,
    StaticTokenVerifier,
    json_depth,
)
from ledger.service import LedgerService, ServiceSettings

SECRET = "test-secret-value"


def quiet_settings(**overrides):
    values = {"host": "127.0.0.1", "port": 8080, "database_path": ":memory:",
              "max_body_bytes": 1_048_576, "drain_timeout_seconds": 5.0}
    values.update(overrides)
    return ServiceSettings(**values)


def operator_verifier(token: str):
    if token == "operator":
        return {"role": "reconciliation_operator", "roles": ("reconciliation_operator",), "source_ids": None}
    if token == "reader-a":
        return {"role": "reader", "roles": ("reader",), "source_ids": ("source-a",)}
    return None


class TokenVerifierTests(unittest.TestCase):
    def test_static_verifier_returns_principal_and_rejects_unknown(self):
        verifier = StaticTokenVerifier({
            "op": Principal("alice", ("reconciliation_operator",)),
            "reader": Principal("bob", ("reader",), ("source-a",)),
        })
        self.assertTrue(verifier.configured)
        self.assertEqual(verifier("op")["roles"], ("reconciliation_operator",))
        self.assertEqual(verifier("reader")["source_ids"], ("source-a",))
        self.assertIsNone(verifier("nope"))
        self.assertIsNone(verifier(""))
        self.assertIsNone(StaticTokenVerifier({})("anything"))

    def test_hmac_token_round_trip_and_tamper_rejection(self):
        clock = [1_000]
        verifier = HmacTokenVerifier(SECRET, clock=lambda: clock[0])
        token = verifier.issue(Principal("alice", ("reconciliation_operator",), ("source-a",)), ttl_seconds=60)
        principal = verifier(token)
        self.assertEqual(principal["sub"], "alice")
        self.assertEqual(principal["roles"], ("reconciliation_operator",))
        self.assertEqual(principal["source_ids"], ("source-a",))

        # Tampered payload segment is rejected by the signature.
        head, segment, signature = token.split(".")
        forged = ".".join([head, segment[:-2], signature])
        self.assertIsNone(verifier(forged))
        # Wrong secret is rejected.
        self.assertIsNone(HmacTokenVerifier("other-secret", clock=lambda: clock[0])(token))
        # Wrong token version / malformed tokens are rejected.
        self.assertIsNone(verifier("v2.abc.def"))
        self.assertIsNone(verifier("garbage"))

    def test_hmac_token_expiry(self):
        clock = [1_000]
        verifier = HmacTokenVerifier(SECRET, clock=lambda: clock[0])
        token = verifier.issue(Principal("alice", ("reader",)), ttl_seconds=10)
        self.assertIsNotNone(verifier(token))
        clock[0] += 11
        self.assertIsNone(verifier(token))

    def test_hmac_requires_secret(self):
        with self.assertRaises(ConfigError):
            HmacTokenVerifier("")


class PolicyTests(unittest.TestCase):
    def test_json_depth_measurement(self):
        self.assertEqual(json_depth({"a": 1}), 1)
        self.assertEqual(json_depth([{"a": [1]}]), 3)
        self.assertEqual(json_depth("scalar"), 0)

    def test_rate_limiter_window(self):
        clock = [0.0]
        limiter = RateLimiter(2, window_seconds=60.0, clock=lambda: clock[0])
        self.assertTrue(limiter.allow("c"))
        self.assertTrue(limiter.allow("c"))
        self.assertFalse(limiter.allow("c"))
        self.assertTrue(limiter.allow("other"))
        clock[0] = 61.0
        self.assertTrue(limiter.allow("c"))
        self.assertFalse(RateLimiter(0).enabled)

    def test_security_headers_and_cors(self):
        policy = SecurityPolicy(cors_origins=("https://app.example.com",), require_tls=True)
        headers = policy.security_headers("https://app.example.com")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("Strict-Transport-Security", headers)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.example.com")
        self.assertNotIn("Access-Control-Allow-Origin", policy.security_headers("https://evil.example.com"))
        self.assertFalse(policy.origin_allowed("https://evil.example.com"))
        self.assertTrue(policy.origin_allowed(None))
        plain = SecurityPolicy()
        self.assertNotIn("Strict-Transport-Security", plain.security_headers())
        self.assertEqual(plain.security_headers()["Cache-Control"], "no-store")

    def test_transport_and_size_limits(self):
        policy = SecurityPolicy(require_tls=True, max_body_bytes=10, max_json_depth=1)
        self.assertTrue(policy.transport_ok("https", None))
        self.assertTrue(policy.transport_ok("http", "https"))
        self.assertFalse(policy.transport_ok("http", None))
        self.assertTrue(SecurityPolicy().transport_ok("http", None))
        self.assertFalse(policy.body_size_ok(11))
        self.assertTrue(policy.body_size_ok(10))
        self.assertFalse(policy.json_depth_ok({"a": {"b": 1}}))
        self.assertTrue(policy.json_depth_ok({"a": 1}))


class ServiceSecurityTests(unittest.TestCase):
    def _service(self, **overrides):
        return LedgerService(quiet_settings(**overrides), token_verifier=operator_verifier).start()

    def test_origin_not_allowed_fails_closed(self):
        service = self._service(cors_origins=("https://app.example.com",))
        try:
            status, body = service.handle("GET", "/reports", headers={
                "Authorization": "Bearer operator", "Origin": "https://evil.example.com"})
            self.assertEqual(status, 403)
            self.assertEqual(body["error"]["code"], "origin_not_allowed")
            status, _ = service.handle("GET", "/reports", headers={
                "Authorization": "Bearer operator", "Origin": "https://app.example.com"})
            self.assertEqual(status, 200)
            headers = service.security_headers("https://app.example.com")
            self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.example.com")
        finally:
            service.stop()

    def test_tls_required_but_probe_paths_exempt(self):
        service = self._service(require_tls=True)
        try:
            self.assertEqual(service.handle("GET", "/health", scheme="http")[0], 200)
            status, body = service.handle("GET", "/reports", headers={"Authorization": "Bearer operator"}, scheme="http")
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "tls_required")
            status, _ = service.handle("GET", "/reports", headers={"Authorization": "Bearer operator",
                                                                   "X-Forwarded-Proto": "https"}, scheme="http")
            self.assertEqual(status, 200)
        finally:
            service.stop()

    def test_rate_limit_returns_429(self):
        service = self._service(rate_limit_per_minute=2)
        try:
            headers = {"Authorization": "Bearer operator"}
            self.assertEqual(service.handle("GET", "/reports", headers=headers, client="9.9.9.9")[0], 200)
            self.assertEqual(service.handle("GET", "/reports", headers=headers, client="9.9.9.9")[0], 200)
            status, body = service.handle("GET", "/reports", headers=headers, client="9.9.9.9")
            self.assertEqual(status, 429)
            self.assertEqual(body["error"]["code"], "rate_limited")
            self.assertEqual(service.handle("GET", "/reports", headers=headers, client="8.8.8.8")[0], 200)
        finally:
            service.stop()

    def test_json_depth_and_content_type_limits(self):
        service = self._service(max_json_depth=2)
        try:
            headers = {"Authorization": "Bearer operator", "Content-Type": "application/json"}
            deep = {"a": {"b": {"c": 1}}}
            status, body = service.handle("POST", "/sources", deep, headers)
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "payload_too_deep")
            status, body = service.handle("POST", "/sources", {"a": 1}, {"Authorization": "Bearer operator",
                                                                        "Content-Type": "text/plain"})
            self.assertEqual(status, 415)
            self.assertEqual(body["error"]["code"], "unsupported_media_type")
        finally:
            service.stop()

    def test_options_preflight_is_empty_and_public(self):
        service = self._service()
        try:
            status, body = service.handle("OPTIONS", "/reconciliations")
            self.assertEqual(status, 204)
            self.assertEqual(body, {"data": {}})
        finally:
            service.stop()

    def test_hmac_token_authenticates_and_expires(self):
        clock = [1_000]
        verifier = HmacTokenVerifier(SECRET, clock=lambda: clock[0])
        service = LedgerService(quiet_settings(), token_verifier=verifier).start()
        try:
            token = verifier.issue(Principal("alice", ("reader",)), ttl_seconds=10)
            self.assertEqual(service.handle("GET", "/reconciliations",
                                            headers={"Authorization": f"Bearer {token}"})[0], 200)
            clock[0] += 11
            status, body = service.handle("GET", "/reconciliations", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(status, 401)
            self.assertEqual(body["error"]["code"], "invalid_token")
        finally:
            service.stop()

    def test_reader_role_cannot_resolve(self):
        service = self._service()
        try:
            status, body = service.handle("GET", "/discrepancies", headers={"Authorization": "Bearer reader-a"})
            self.assertEqual(status, 200)
            status, body = service.handle(
                "POST", "/discrepancies/does-not-exist/resolve",
                {"resolution_type": "MANUAL_APPROVED", "reason": "x"},
                {"Authorization": "Bearer reader-a", "Content-Type": "application/json"})
            self.assertEqual(status, 403)
            self.assertEqual(body["error"]["code"], "forbidden")
        finally:
            service.stop()

    def test_production_requires_configured_identity(self):
        settings = ServiceSettings(base=Settings(environment="production"), database_path=":memory:")
        service = LedgerService(settings)
        with self.assertRaises(ConfigError):
            service.start()

    def test_credentials_never_reach_telemetry(self):
        telemetry = InMemoryTelemetrySink()
        service = LedgerService(quiet_settings(), telemetry=telemetry, token_verifier=operator_verifier).start()
        try:
            service.handle("GET", "/reports", headers={"Authorization": "Bearer super-secret-token"})
        finally:
            service.stop()
        serialized = json.dumps(telemetry.events)
        self.assertNotIn("super-secret-token", serialized)
        self.assertNotIn("Authorization", serialized)


if __name__ == "__main__":
    unittest.main()
