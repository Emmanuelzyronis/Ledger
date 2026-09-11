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
import uuid
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .api import LedgerAPI, APIError
from .config import ConfigError, Settings
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase
from .security import HmacTokenVerifier, Principal, SecurityPolicy, StaticTokenVerifier

MAX_PORT = 65535
PUBLIC_PATHS = {"health", "ready"}
JSON_CONTENT_TYPE = "application/json"
API_VERSION_PREFIX = "v1"


def _looks_like_version(segment: str) -> bool:
    return len(segment) > 1 and segment[0] == "v" and segment[1:].isdigit()


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if key.casefold() == target:
            return value
    return None


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Validated, non-secret runtime settings for the service process."""

    database_path: str = "ledger.sqlite3"
    host: str = "127.0.0.1"
    port: int = 8080
    max_body_bytes: int = 1_048_576
    max_json_depth: int = 32
    drain_timeout_seconds: float = 10.0
    cors_origins: tuple[str, ...] = ()
    rate_limit_per_minute: int = 0
    require_tls: bool = False
    token_secret: str | None = None
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

        max_json_depth = _positive_int(values, "LEDGER_MAX_JSON_DEPTH", 32)
        rate_limit_per_minute = _non_negative_int(values, "LEDGER_RATE_LIMIT_PER_MINUTE", 0)
        require_tls = _boolean(values, "LEDGER_REQUIRE_TLS", base.environment == "production")
        token_secret = (values.get("LEDGER_TOKEN_SECRET") or "").strip() or None

        cors_origins = tuple(item.strip() for item in values.get("LEDGER_CORS_ORIGINS", "").split(",") if item.strip())
        for origin in cors_origins:
            if not origin.startswith(("http://", "https://")):
                raise ConfigError("LEDGER_CORS_ORIGINS entries must be http(s) origins")

        return cls(database_path=database_path, host=host, port=port,
                   max_body_bytes=max_body_bytes, max_json_depth=max_json_depth,
                   drain_timeout_seconds=drain_timeout, cors_origins=cors_origins,
                   rate_limit_per_minute=rate_limit_per_minute, require_tls=require_tls,
                   token_secret=token_secret, base=base)


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < 1:
        raise ConfigError(f"{name} must be positive")
    return value


def _non_negative_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < 0:
        raise ConfigError(f"{name} must not be negative")
    return value


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized not in {"true", "false"}:
        raise ConfigError(f"{name} must be true or false")
    return normalized == "true"


def env_token_verifier(environ: Mapping[str, str] | None = None) -> Callable[[str], Mapping[str, Any] | None]:
    """Development/local opaque-token verifier.

    ``LEDGER_API_TOKENS`` is a comma-separated list of ``token:role[:source|source]``
    entries. Comparison is constant-time over every registered entry and tokens
    are never logged. Production should use ``LEDGER_TOKEN_SECRET`` with
    :class:`~ledger.security.HmacTokenVerifier`, or replace the verifier with an
    OIDC/JWKS provider at the same boundary.
    """
    values = os.environ if environ is None else environ
    registered: dict[str, Principal] = {}
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
        registered[token] = Principal(subject=role, roles=(role,), source_ids=source_ids)
    return StaticTokenVerifier(registered)


class LedgerService:
    """Owns the process-level lifecycle around an in-process LedgerAPI."""

    def __init__(self, settings: ServiceSettings | None = None, *, telemetry: TelemetrySink | None = None,
                 token_verifier: Callable[[str], Mapping[str, Any] | None] | None = None) -> None:
        self.settings = settings or ServiceSettings.from_env()
        self.telemetry = telemetry
        self.security = SecurityPolicy(
            max_body_bytes=self.settings.max_body_bytes,
            max_json_depth=self.settings.max_json_depth,
            cors_origins=self.settings.cors_origins,
            require_tls=self.settings.require_tls,
            rate_limit_per_minute=self.settings.rate_limit_per_minute,
        )
        if token_verifier is not None:
            self._token_verifier = token_verifier
        elif self.settings.token_secret:
            self._token_verifier = HmacTokenVerifier(self.settings.token_secret)
        else:
            self._token_verifier = env_token_verifier(os.environ)
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
        if self.settings.base.environment == "production" and not getattr(self._token_verifier, "configured", True):
            raise ConfigError("production requires LEDGER_TOKEN_SECRET or LEDGER_API_TOKENS")
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
            "tls_required": self.settings.require_tls,
            "rate_limit_per_minute": self.settings.rate_limit_per_minute,
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
               headers: Mapping[str, str] | None = None, *,
               client: str | None = None, scheme: str = "http") -> tuple[int, dict[str, Any]]:
        """Handle one HTTP request with request-scoped drain accounting."""
        if self._api is None:
            raise RuntimeError("service is not started")
        with self._request_lock:
            self._active_requests += 1
            self._drained.clear()
        try:
            return self._handle(method, path, body, headers, client, scheme)
        finally:
            with self._request_lock:
                self._active_requests -= 1
                if self._active_requests == 0:
                    self._drained.set()

    def security_headers(self, origin: str | None = None) -> dict[str, str]:
        """Response headers every transport must attach (security + CORS)."""
        return self.security.security_headers(origin)

    def _handle(self, method: str, path: str, body: Any, headers: Mapping[str, str] | None,
                client: str | None, scheme: str) -> tuple[int, dict[str, Any]]:
        headers = headers or {}
        correlation_id = _header(headers, "X-Correlation-ID") or str(uuid.uuid4())
        parsed = urlsplit(path)
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if segments and segments[0] == API_VERSION_PREFIX:
            segments = segments[1:]
        elif segments and _looks_like_version(segments[0]):
            return 404, self._failure("unsupported_api_version",
                                      f"only /{API_VERSION_PREFIX} is supported", correlation_id)
        route = segments[0] if segments else ""
        normalized = "/" + "/".join(segments)
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        origin = _header(headers, "Origin")
        if not self.security.origin_allowed(origin):
            return 403, self._failure("origin_not_allowed", "request origin is not allowed", correlation_id)
        # Unauthenticated liveness/readiness probes are exempt from TLS so a
        # platform can probe the pod directly; they expose no business data.
        if route not in PUBLIC_PATHS and not self.security.transport_ok(scheme, _header(headers, "X-Forwarded-Proto")):
            return 400, self._failure("tls_required", "HTTPS is required for this environment", correlation_id)
        if not self.security.rate_limiter.allow(client or "unknown"):
            return 429, self._failure("rate_limited", "request rate limit exceeded", correlation_id)
        if body is not None and not self.security.json_depth_ok(body):
            return 400, self._failure("payload_too_deep", "request body exceeds the JSON depth limit", correlation_id)
        if body is not None and method.upper() in {"POST", "PUT", "PATCH"}:
            content_type = (_header(headers, "Content-Type") or "").split(";")[0].strip().lower()
            if content_type != JSON_CONTENT_TYPE:
                return 415, self._failure("unsupported_media_type", "request body must be application/json", correlation_id)
        if method.upper() == "OPTIONS":
            return 204, {"data": {}}
        if method.upper() == "GET" and route in PUBLIC_PATHS:
            return self._public_probe(route)
        # Propagate one correlation id across the service and API layers so an
        # error returned by either boundary carries the same identifier.
        api_headers = dict(headers)
        api_headers["X-Correlation-ID"] = correlation_id
        try:
            return self.api.handle(method, normalized, body, api_headers)
        except APIError as exc:
            return exc.status, {"error": {"code": exc.code, "message": exc.message},
                                "correlation_id": correlation_id}

    @staticmethod
    def _failure(code: str, message: str, correlation_id: str | None = None) -> dict[str, Any]:
        return {"error": {"code": code, "message": message},
                "correlation_id": correlation_id or str(uuid.uuid4())}

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
        headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}
        response_headers = self.service.security_headers(_header(headers, "Origin"))
        correlation_id = _header(headers, "X-Correlation-ID") or str(uuid.uuid4())
        body = b""
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if not self.service.security.body_size_ok(len(body)):
                await self._respond(send, 413, {"error": {"code": "payload_too_large",
                                                          "message": "request body exceeds the configured limit"},
                                                "correlation_id": correlation_id},
                                    response_headers)
                return
        payload: Any = None
        if body:
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._respond(send, 400, {"error": {"code": "invalid_json", "message": "request body must be valid JSON"},
                                                "correlation_id": correlation_id},
                                    response_headers)
                return
        path = scope.get("path", "/")
        query = scope.get("query_string", b"")
        if query:
            path = f"{path}?{query.decode('latin-1')}"
        import asyncio

        client = (scope.get("client") or (None,))[0]
        try:
            status, response = await asyncio.to_thread(
                self.service.handle, scope.get("method", "GET"), path, payload, headers,
                client=client, scheme=scope.get("scheme", "http"))
        except Exception:  # pragma: no cover - defensive boundary
            await self._respond(send, 500, {"error": {"code": "internal_error", "message": "internal server error"},
                                            "correlation_id": correlation_id}, response_headers)
            return
        await self._respond(send, status, response, response_headers)

    @staticmethod
    async def _respond(send: Callable[[Mapping[str, Any]], Any], status: int, payload: Mapping[str, Any],
                       extra_headers: Mapping[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        for name, value in (extra_headers or {}).items():
            headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def create_app(settings: ServiceSettings | None = None, **kwargs: Any) -> LedgerASGI:
    """ASGI factory: ``uvicorn ledger.service:create_app --factory``."""
    resolved = settings or ServiceSettings.from_env()
    return LedgerASGI(LedgerService(resolved, **kwargs))


def app() -> LedgerASGI:  # pragma: no cover - convenience entrypoint
    return create_app()
