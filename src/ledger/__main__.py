"""Dependency-free local runner: ``python -m ledger``.

Serves the same ASGI application boundary over a stdlib threading HTTP server so
the service can be reproduced without third-party packages. A production
deployment may instead run ``uvicorn ledger.service:create_app --factory``.
"""

from __future__ import annotations

import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .service import LedgerService, ServiceSettings
from .service import TextResponse
from .observability import JsonLogSink


def build_handler(service: LedgerService) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to a started service."""

    class LedgerRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "LEDGER/0.1"

        def _dispatch(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, {"error": {"code": "invalid_request", "message": "invalid Content-Length"}})
                return
            raw = self.rfile.read(length) if length else b""
            payload: Any = None
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    self._send(400, {"error": {"code": "invalid_json", "message": "request body must be valid JSON"}})
                    return
            headers = {key: value for key, value in self.headers.items()}
            status, response = service.handle(method, self.path, payload, headers,
                                              client=self.client_address[0], scheme="http")
            self._send(status, response, headers)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            self._dispatch("POST")

        def log_message(self, format: str, *args: Any) -> None:
            # Structured lifecycle telemetry is emitted by the service; the
            # stdlib access log is intentionally suppressed so it cannot leak
            # request bodies or credentials.
            return

        def _send(self, status: int, payload: Any, request_headers: Any = None) -> None:
            if isinstance(payload, TextResponse):
                body = payload.body.encode("utf-8")
                content_type = payload.content_type
                correlation_id = None
            else:
                body = json.dumps(payload).encode("utf-8")
                content_type = "application/json"
                correlation_id = payload.get("correlation_id") if isinstance(payload, dict) else None
            origin = None
            if request_headers is not None:
                origin = request_headers.get("Origin") or request_headers.get("origin")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if correlation_id:
                self.send_header("X-Correlation-ID", correlation_id)
            for name, value in service.security_headers(origin).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return LedgerRequestHandler


def serve(service: LedgerService, *, ready: threading.Event | None = None) -> ThreadingHTTPServer:
    """Start a threading HTTP server for a started service (non-blocking)."""
    server = ThreadingHTTPServer((service.settings.host, service.settings.port), build_handler(service))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="ledger-http", daemon=True).start()
    if ready is not None:
        ready.set()
    return server


def main(argv: list[str] | None = None) -> int:
    settings = ServiceSettings.from_env()
    telemetry = JsonLogSink(service="ledger") if settings.base.telemetry_enabled else None
    service = LedgerService(settings, telemetry=telemetry).start()
    stop = threading.Event()

    def request_shutdown(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    server = serve(service)
    print(f"LEDGER listening on http://{settings.host}:{settings.port} (env={settings.base.environment})")
    try:
        while not stop.is_set():
            stop.wait(0.5)
    finally:
        print("LEDGER shutting down: draining in-flight requests")
        server.shutdown()
        server.server_close()
        service.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
