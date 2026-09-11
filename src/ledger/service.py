"""Deployment-neutral HTTP service boundary, lifecycle, and process model.

The domain and API layers stay framework-independent. This module owns the
infrastructure concerns of a service process: validated runtime settings,
database lifecycle, health/readiness, graceful drain, and structured
startup/shutdown telemetry.

Service strategy (Architecture D-010): a single-process ASGI application with
synchronous, request-scoped batch execution. There are no background workers or
queues in the portfolio cut; every authoritative write happens inside the API
request that triggers it. The application is importable as
``ledger.service:create_app`` and can be served by any ASGI server; a
dependency-free stdlib runner is provided by ``python -m ledger``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
import threading
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .api import LedgerAPI, APIError
from .config import ConfigError, Settings
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase

MAX_PORT = 65535
PUBLIC_PATHS = {"health", "ready"}


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Validated, non-secret runtime settings for the service process."""

    database_path: str = "ledger.sqlite3"
    host: str = "127.0.0.1"
    port: int = 8080
    max_body_bytes: int = 1_048_576
    drain_timeout_seconds: float = 10.0
    base: Settings = field(default_factory=Settings)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ServiceSettings":
        values = os.environ if environ is None else environ
        base = Settings.from_env(values)

        host = values.get("LEDGER_HOST", "127.0.0.1").strip()
        if not host:
            raise ConfigError("LEDGER_HOST must not be empty")

        port = _positive_int(values, "LEDGER_PORT", 8080)
        if port > MAX_PORT:
            raise ConfigError(f"LEDGER_PORT must be between 1 and {MAX_PORT}")

        max_body_bytes = _positive_int(values, "LEDGER_MAX_BODY_BYTES", 1_048_576)

        raw_drain = values.get("LEDGER_DRAIN_TIMEOUT_SECONDS", "10").strip()
        try:
            drain_timeout = float(raw_drain)
        except ValueError as exc:
            raise ConfigError("LEDGER_DRAIN_TIMEOUT_SECONDS must be a number") from exc
        if drain_timeout < 0:
            raise ConfigError("LEDGER_DRAIN_TIMEOUT_SECONDS must not be negative")

        database_path = values.get("LEDGER_DATABASE_PATH", "ledger.sqlite3").strip()
        if not database_path:
            raise ConfigError("LEDGER_DATABASE_PATH must not be empty")

        return cls(database_path=database_path, host=host, port=port,
                   max_body_bytes=max_body_bytes, drain_timeout_seconds=drain_timeout, base=base)


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < 1:
        raise ConfigError(f"{name} must be positive")
    return value


def env_token_verifier(environ: Mapping[str, str] | None = None) -> Callable[[str], Mapping[str, Any] | None]:
    """Baseline opaque-token verifier.

    ``LEDGER_API_TOKENS`` is a comma-separated list of ``token:role[:source|source]``
    entries. Tokens are compared by exact match and are never logged. EPIC 3
    (EMM-79) replaces this with the production identity provider and
    constant-time verification.
    """
    values = os.environ if environ is None else environ
    registered: dict[str, Mapping[str, Any]] = {}
    for entry in values.get("LEDGER_API_TOKENS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        token = parts[0].strip()
        if not token:
            raise ConfigError("LEDGER_API_TOKENS contains an empty token")
        role = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "reconciliation_operator"
        source_ids = tuple(item for item in parts[2].split("|") if item) if len(parts) > 2 else None
        registered[token] = {"role": role, "roles": (role,), "source_ids": source_ids}

    def verify(token: str) -> Mapping[str, Any] | None:
        return registered.get(token)

    return verify


class LedgerService:
    """Owns the process-level lifecycle around an in-process LedgerAPI."""

    def __init__(self, settings: ServiceSettings | None = None, *, telemetry: TelemetrySink | None = None,
                 token_verifier: Callable[[str], Mapping[str, Any] | None] | None = None) -> None:
        self.settings = settings or ServiceSettings.from_env()
        self.telemetry = telemetry
        self._token_verifier = token_verifier or env_token_verifier()
        self._database: LedgerDatabase | None = None
        self._api: LedgerAPI | None = None
        self._state_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._active_requests = 0
        self._drained = threading.Event()
        self._drained.set()

    # -- lifecycle -------------------------------------------------------
    @property
    def started(self) -> bool:
        return self._api is not None

    @property
    def database(self) -> LedgerDatabase:
        if self._database is None:
            raise RuntimeError("service is not started")
        return self._database

    @property
    def api(self) -> LedgerAPI:
        if self._api is None:
            raise RuntimeError("service is not started")
        return self._api

    def start(self) -> "LedgerService":
        """Open the authoritative database and bind the API. Idempotent."""
        with self._state_lock:
            if self._api is not None:
                return self
            database = LedgerDatabase(self.settings.database_path)
            self._database = database
            self._api = LedgerAPI(database, token_verifier=self._token_verifier, telemetry=self.telemetry)
        self._log("ledger.service.started", {
            "environment": self.settings.base.environment,
            "database_path": self.settings.database_path,
            "host": self.settings.host,
            "port": self.settings.port,
        })
        return self

    def stop(self) -> None:
        """Drain in-flight work, then close the database. Idempotent."""
        with self._state_lock:
            database, api = self._database, self._api
            self._database, self._api = None, None
        if api is None:
            return
        drained = self._drained.wait(timeout=self.settings.drain_timeout_seconds)
        if not drained:
            self._log("ledger.service.drain_timeout", {
                "active_requests": self._active_requests,
                "drain_timeout_seconds": self.settings.drain_timeout_seconds,
            })
        if database is not None:
            database.close()
        self._log("ledger.service.stopped", {
            "active_requests": self._active_requests,
            "drained": drained,
        })

    def __enter__(self) -> "LedgerService":
        return self.start()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop()

    # -- request handling ------------------------------------------------
    def handle(self, method: str, path: str, body: Any = None,
               headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
        """Handle one HTTP request with request-scoped drain accounting."""
        if self._api is None:
            raise RuntimeError("service is not started")
        with self._request_lock:
            self._active_requests += 1
            self._drained.clear()
        try:
            return self._handle(method, path, body, headers)
        finally:
            with self._request_lock:
                self._active_requests -= 1
                if self._active_requests == 0:
                    self._drained.set()

    def _handle(self, method: str, path: str, body: Any,
                headers: Mapping[str, str] | None) -> tuple[int, dict[str, Any]]:
        route = urlsplit(path).path.strip("/")
        if method.upper() == "GET" and route in PUBLIC_PATHS:
            return self._public_probe(route)
        try:
            return self.api.handle(method, path, body, headers)
        except APIError as exc:
            return exc.status, {"error": {"code": exc.code, "message": exc.message}}

    def _public_probe(self, route: str) -> tuple[int, dict[str, Any]]:
        if route == "health":
            return 200, {"data": {"status": "ok", "application": "ok"}, "correlation_id": "health"}
        try:
            self.database.connection.execute("SELECT 1").fetchone()
        except Exception:
            return 503, {"data": {"status": "degraded", "application": "ok", "database": "unavailable"},
                         "correlation_id": "ready"}
        return 200, {"data": {"status": "ok", "application": "ok", "database": "ok"}, "correlation_id": "ready"}

    @property
    def active_requests(self) -> int:
        with self._request_lock:
            return self._active_requests

    def _log(self, name: str, attributes: Mapping[str, Any]) -> None:
        if self.telemetry is not None:
            self.telemetry.emit(TelemetryEvent(name, CorrelationContext(), dict(attributes)))


class LedgerASGI:
    """Minimal ASGI application exposing :class:`LedgerService` over HTTP."""

    def __init__(self, service: LedgerService) -> None:
        self.service = service

    async def __call__(self, scope: Mapping[str, Any], receive: Callable[[], Any],
                       send: Callable[[Mapping[str, Any]], Any]) -> None:
        kind = scope.get("type")
        if kind == "lifespan":
            await self._lifespan(receive, send)
            return
        if kind == "http":
            await self._http(scope, receive, send)
            return
        raise RuntimeError(f"unsupported ASGI scope type: {kind!r}")

    async def _lifespan(self, receive: Callable[[], Any], send: Callable[[Mapping[str, Any]], Any]) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    self.service.start()
                except Exception as exc:  # pragma: no cover - defensive startup path
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                self.service.stop()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _http(self, scope: Mapping[str, Any], receive: Callable[[], Any],
                    send: Callable[[Mapping[str, Any]], Any]) -> None:
        body = b""
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > self.service.settings.max_body_bytes:
                await self._respond(send, 413, {"error": {"code": "payload_too_large",
                                                          "message": "request body exceeds the configured limit"}})
                return
        headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}
        payload: Any = None
        if body:
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._respond(send, 400, {"error": {"code": "invalid_json", "message": "request body must be valid JSON"}})
                return
        path = scope.get("path", "/")
        query = scope.get("query_string", b"")
        if query:
            path = f"{path}?{query.decode('latin-1')}"
        import asyncio

        try:
            status, response = await asyncio.to_thread(self.service.handle, scope.get("method", "GET"), path, payload, headers)
        except Exception as exc:  # pragma: no cover - defensive boundary
            await self._respond(send, 500, {"error": {"code": "internal_error", "message": str(exc)}})
            return
        await self._respond(send, status, response)

    @staticmethod
    async def _respond(send: Callable[[Mapping[str, Any]], Any], status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def create_app(settings: ServiceSettings | None = None, **kwargs: Any) -> LedgerASGI:
    """ASGI factory: ``uvicorn ledger.service:create_app --factory``."""
    resolved = settings or ServiceSettings.from_env()
    return LedgerASGI(LedgerService(resolved, **kwargs))


def app() -> LedgerASGI:  # pragma: no cover - convenience entrypoint
    return create_app()
