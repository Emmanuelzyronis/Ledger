"""Layer-2 (portfolio cut) service boundary, lifecycle, and process-model tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from ledger.__main__ import serve
from ledger.config import ConfigError
from ledger.observability import InMemoryTelemetrySink
from ledger.service import LedgerASGI, LedgerService, ServiceSettings, env_token_verifier


NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


def operator_verifier(token: str):
    if token == "operator":
        return {"role": "reconciliation_operator", "roles": ("reconciliation_operator",), "source_ids": None}
    if token == "reader":
        return {"role": "reader", "roles": ("reader",), "source_ids": ("source-a",)}
    return None


def quiet_settings(**overrides):
    values = {"host": "127.0.0.1", "port": 8080, "database_path": ":memory:",
              "max_body_bytes": 1_048_576, "drain_timeout_seconds": 5.0}
    values.update(overrides)
    return ServiceSettings(**values)


def asgi_request(app, method, path, payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    scope = {"type": "http", "method": method, "path": path, "query_string": b"",
             "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]}
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body_message = next(message for message in sent if message["type"] == "http.response.body")
    return start["status"], json.loads(body_message["body"])


def asgi_lifespan(app):
    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan"}, receive, send))
    return sent


class ServiceSettingsTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        settings = ServiceSettings.from_env({})
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.database_path, "ledger.sqlite3")
        self.assertEqual(settings.base.environment, "development")

    def test_invalid_values_are_rejected(self):
        for environ in ({"LEDGER_PORT": "0"}, {"LEDGER_PORT": "70000"}, {"LEDGER_PORT": "abc"},
                        {"LEDGER_HOST": "  "}, {"LEDGER_DRAIN_TIMEOUT_SECONDS": "-1"},
                        {"LEDGER_MAX_BODY_BYTES": "0"}, {"LEDGER_ENV": "staging"}):
            with self.assertRaises(ConfigError, msg=environ):
                ServiceSettings.from_env(environ)

    def test_env_token_verifier_shape(self):
        verifier = env_token_verifier({"LEDGER_API_TOKENS": "abc:reader:source-a|source-b,xyz"})
        self.assertEqual(verifier("abc")["source_ids"], ("source-a", "source-b"))
        self.assertEqual(verifier("xyz")["role"], "reconciliation_operator")
        self.assertIsNone(verifier("missing"))


class ServiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.telemetry = InMemoryTelemetrySink()
        self.service = LedgerService(quiet_settings(), telemetry=self.telemetry, token_verifier=operator_verifier)

    def tearDown(self):
        self.service.stop()

    def test_start_is_idempotent_and_serves_api(self):
        self.assertFalse(self.service.started)
        self.service.start()
        self.service.start()
        status, body = self.service.handle(
            "POST", "/sources",
            {"source_id": "source-a", "name": "Source A", "schema_versions": ["source_a.v1"]},
            {"Authorization": "Bearer operator"})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["source_id"], "source-a")

    def test_health_and_readiness_are_public(self):
        self.service.start()
        status, body = self.service.handle("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], {"status": "ok", "application": "ok"})
        status, body = self.service.handle("GET", "/ready")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["database"], "ok")

    def test_readiness_fails_when_database_is_unavailable(self):
        self.service.start()
        self.service.database.close()
        status, body = self.service.handle("GET", "/ready")
        self.assertEqual(status, 503)
        self.assertEqual(body["data"]["database"], "unavailable")
        # Liveness stays up: the process is still responsive.
        self.assertEqual(self.service.handle("GET", "/health")[0], 200)

    def test_unauthenticated_api_request_is_rejected(self):
        self.service.start()
        self.assertEqual(self.service.handle("GET", "/reports")[0], 401)
        self.assertEqual(self.service.handle("GET", "/reports", headers={"Authorization": "Bearer nope"})[0], 401)

    def test_graceful_shutdown_drains_in_flight_requests(self):
        release = threading.Event()
        entered = threading.Event()

        def blocking_verifier(token: str):
            entered.set()
            release.wait(timeout=5)
            return {"role": "reader", "roles": ("reader",), "source_ids": None}

        service = LedgerService(quiet_settings(drain_timeout_seconds=5.0),
                                token_verifier=blocking_verifier)
        service.start()
        result: list[object] = []

        def worker():
            result.append(service.handle("GET", "/reports", headers={"Authorization": "Bearer any"}))

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(entered.wait(timeout=5))
        stopped = threading.Event()

        def stopper():
            service.stop()
            stopped.set()

        stop_thread = threading.Thread(target=stopper)
        stop_thread.start()
        self.assertFalse(stopped.wait(timeout=0.3), "stop() returned before active work drained")
        release.set()
        thread.join(timeout=5)
        stop_thread.join(timeout=5)
        self.assertTrue(stopped.is_set())
        self.assertEqual(result[0][0], 200)
        self.assertFalse(service.started)

    def test_structured_lifecycle_telemetry_has_no_secrets(self):
        self.service.start()
        self.service.stop()
        names = [event["name"] for event in self.telemetry.events]
        self.assertIn("ledger.service.started", names)
        self.assertIn("ledger.service.stopped", names)
        text = json.dumps(self.telemetry.events)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("Authorization", text)


class AsgiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.telemetry = InMemoryTelemetrySink()
        self.service = LedgerService(quiet_settings(), telemetry=self.telemetry, token_verifier=operator_verifier)
        self.app = LedgerASGI(self.service)

    def tearDown(self):
        self.service.stop()

    def test_lifespan_starts_and_stops_the_service(self):
        sent = asgi_lifespan(self.app)
        self.assertEqual(sent[0]["type"], "lifespan.startup.complete")
        self.assertEqual(sent[1]["type"], "lifespan.shutdown.complete")
        self.assertFalse(self.service.started)

    def test_http_health_and_authenticated_reports(self):
        self.service.start()
        status, body = asgi_request(self.app, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["application"], "ok")
        status, body = asgi_request(self.app, "GET", "/reports", headers={"Authorization": "Bearer operator"})
        self.assertEqual(status, 200)
        self.assertIn("outcomes", body["data"])

    def test_http_rejects_invalid_json(self):
        self.service.start()
        scope = {"type": "http", "method": "POST", "path": "/sources", "query_string": b"",
                 "headers": [(b"authorization", b"Bearer operator")]}
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"{not json", "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(self.app(scope, receive, send))
        self.assertEqual(sent[0]["status"], 400)

    def test_oversized_body_is_rejected(self):
        service = LedgerService(quiet_settings(max_body_bytes=8), token_verifier=operator_verifier)
        service.start()
        try:
            scope = {"type": "http", "method": "POST", "path": "/sources", "query_string": b"",
                     "headers": [(b"authorization", b"Bearer operator")]}
            sent = []

            async def receive():
                return {"type": "http.request", "body": b"x" * 64, "more_body": False}

            async def send(message):
                sent.append(message)

            asyncio.run(LedgerASGI(service)(scope, receive, send))
            self.assertEqual(sent[0]["status"], 413)
        finally:
            service.stop()


class HttpProcessTests(unittest.TestCase):
    def test_http_roundtrip_and_file_backed_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "ledger.sqlite3")
            settings = quiet_settings(port=0, database_path=database_path)
            service = LedgerService(settings, token_verifier=operator_verifier).start()
            server = serve(service)
            port = server.server_address[1]

            def call(method, path, payload=None, token="operator"):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}", method=method,
                    data=json.dumps(payload).encode() if payload is not None else None,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            try:
                status, _ = call("GET", "/health", token="none")
                self.assertEqual(status, 200)
                status, body = call("POST", "/sources",
                                    {"source_id": "source-a", "name": "Source A", "schema_versions": ["source_a.v1"]})
                self.assertEqual(status, 200)
                status, body = call("POST", "/batches",
                                    {"source_id": "source-a", "external_batch_id": "ext-1", "schema_version": "source_a.v1"})
                self.assertEqual(status, 200)
                batch_id = body["data"]["batch_id"]
                status, body = call("POST", f"/batches/{batch_id}/records",
                                    {"payload": {"record_id": "A-1", "occurred_at": "2026-09-01", "amount": "10.00",
                                                 "currency": "USD", "direction": "CREDIT"}})
                self.assertEqual(status, 200)
                self.assertEqual(body["data"]["status"], "ACCEPTED")
                status, body = call("GET", "/reports")
                self.assertEqual(status, 200)
                self.assertEqual(body["data"]["reconciliation_count"], 0)
            finally:
                server.shutdown()
                server.server_close()
                service.stop()

            # Restart from the same configuration/path: authoritative state persists.
            restarted = LedgerService(settings, token_verifier=operator_verifier).start()
            restarted_server = serve(restarted)
            restarted_port = restarted_server.server_address[1]
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{restarted_port}/batches/{batch_id}", method="GET",
                    headers={"Authorization": "Bearer operator"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    body = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(body["data"]["batch_id"], batch_id)
                self.assertEqual(body["data"]["counters"]["accepted_count"], 1)
            finally:
                restarted_server.shutdown()
                restarted_server.server_close()
                restarted.stop()


if __name__ == "__main__":
    unittest.main()
