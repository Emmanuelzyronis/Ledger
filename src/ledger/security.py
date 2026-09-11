"""Baseline security boundary for the LEDGER service (EPIC 3 / EMM-79).

Scope is an explicit baseline, not an exhaustive hardening program:

* pluggable bearer-token verification with constant-time comparison and expiry;
* least-privilege principals (roles + source scoping) enforced by the API layer;
* request body, JSON depth, and content-type limits;
* in-process fixed-window rate limiting;
* CORS allowlisting and security response headers;
* explicit TLS transport expectations.

Secrets are supplied through the runtime environment and never logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import threading
import time
from typing import Any, Mapping

from .config import ConfigError

TOKEN_VERSION = "v1"
READER_ROLE = "reader"
OPERATOR_ROLE = "reconciliation_operator"
KNOWN_ROLES = (READER_ROLE, OPERATOR_ROLE)


@dataclass(frozen=True, slots=True)
class Principal:
    """Least-privilege caller identity."""

    subject: str
    roles: tuple[str, ...]
    source_ids: tuple[str, ...] | None = None

    def as_mapping(self) -> dict[str, Any]:
        return {
            "sub": self.subject,
            "role": self.roles[0] if self.roles else None,
            "roles": self.roles,
            "source_ids": self.source_ids,
        }


class StaticTokenVerifier:
    """Exact-match registry with constant-time comparison over every entry.

    All entries are compared on every call so a caller cannot learn which token
    matched, or how many tokens exist, from response timing.
    """

    def __init__(self, registry: Mapping[str, "Principal | Mapping[str, Any]"]) -> None:
        entries: list[tuple[bytes, Principal]] = []
        for token, principal in registry.items():
            if not token:
                raise ConfigError("token registry contains an empty token")
            resolved = principal if isinstance(principal, Principal) else Principal(
                subject=str(principal.get("sub") or principal.get("role") or "unknown"),
                roles=tuple(principal.get("roles") or ((principal["role"],) if principal.get("role") else ())),
                source_ids=tuple(principal["source_ids"]) if principal.get("source_ids") else None,
            )
            entries.append((token.encode("utf-8"), resolved))
        self._entries = tuple(entries)

    @property
    def configured(self) -> bool:
        return bool(self._entries)

    def __call__(self, token: str) -> dict[str, Any] | None:
        candidate = token.encode("utf-8")
        matched: Principal | None = None
        for registered, principal in self._entries:
            if hmac.compare_digest(registered, candidate):
                matched = principal
        return matched.as_mapping() if matched is not None else None


class HmacTokenVerifier:
    """Baseline signed-token verifier (constant-time, expiring, dependency-free).

    Format: ``v1.<base64url(payload_json)>.<base64url(hmac_sha256(secret, "v1." + payload))>``.
    This is deliberately not JWT; an OIDC/JWKS provider can replace this verifier
    at the same boundary without changing the API layer.
    """

    def __init__(self, secret: str, *, leeway_seconds: int = 0, clock: Any = None) -> None:
        if not secret:
            raise ConfigError("token secret must not be empty")
        self._secret = secret.encode("utf-8")
        self._leeway = max(0, int(leeway_seconds))
        self._clock = clock or (lambda: int(time.time()))

    @property
    def configured(self) -> bool:
        return True

    def issue(self, principal: Principal, *, ttl_seconds: int = 3600, issued_at: int | None = None) -> str:
        now = int(self._clock()) if issued_at is None else issued_at
        payload = dict(principal.as_mapping())
        payload["iat"] = now
        payload["exp"] = now + int(ttl_seconds)
        segment = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(self._secret, f"{TOKEN_VERSION}.{segment}".encode("ascii"), hashlib.sha256).digest()
        return f"{TOKEN_VERSION}.{segment}.{_b64encode(signature)}"

    def __call__(self, token: str) -> dict[str, Any] | None:
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_VERSION:
            return None
        segment, signature = parts[1], parts[2]
        expected = hmac.new(self._secret, f"{TOKEN_VERSION}.{segment}".encode("ascii"), hashlib.sha256).digest()
        try:
            provided = _b64decode(signature)
        except ValueError:
            return None
        if not hmac.compare_digest(expected, provided):
            return None
        try:
            payload = json.loads(_b64decode(segment).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        expires = payload.get("exp")
        if not isinstance(expires, int) or expires < int(self._clock()) - self._leeway:
            return None
        subject = payload.get("sub")
        roles = payload.get("roles") or ([payload["role"]] if payload.get("role") else [])
        if not subject or not roles:
            return None
        source_ids = payload.get("source_ids")
        return {"sub": str(subject), "role": roles[0], "roles": tuple(roles),
                "source_ids": tuple(source_ids) if source_ids else None}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def json_depth(value: Any) -> int:
    """Maximum nesting depth of a decoded JSON value (scalars are depth 0)."""
    if isinstance(value, dict):
        return 1 + max((json_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((json_depth(item) for item in value), default=0)
    return 0


class RateLimiter:
    """In-process fixed-window rate limiter keyed by client identity."""

    def __init__(self, limit_per_minute: int, *, window_seconds: float = 60.0,
                 clock: Any = None, max_keys: int = 10_000) -> None:
        if limit_per_minute < 0:
            raise ConfigError("rate limit must not be negative")
        self.limit = limit_per_minute
        self.window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._max_keys = max_keys
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def allow(self, key: str) -> bool:
        if not self.enabled:
            return True
        now = self._clock()
        with self._lock:
            if len(self._buckets) > self._max_keys:
                self._buckets = {item: value for item, value in self._buckets.items()
                                 if now - value[0] < self.window_seconds}
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= self.window_seconds:
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            return count <= self.limit


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    """Explicit, testable request-boundary policy."""

    max_body_bytes: int = 1_048_576
    max_json_depth: int = 32
    cors_origins: tuple[str, ...] = ()
    require_tls: bool = False
    rate_limit_per_minute: int = 0
    rate_limiter: RateLimiter = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate_limiter", RateLimiter(self.rate_limit_per_minute))

    def security_headers(self, origin: str | None = None) -> dict[str, str]:
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        }
        if self.require_tls:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if origin and origin in self.cors_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
            headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Correlation-ID"
            headers["Access-Control-Max-Age"] = "600"
        return headers

    def origin_allowed(self, origin: str | None) -> bool:
        return origin is None or origin in self.cors_origins

    def transport_ok(self, scheme: str, forwarded_proto: str | None) -> bool:
        if not self.require_tls:
            return True
        effective = (forwarded_proto or scheme or "http").split(",")[0].strip().lower()
        return effective == "https"

    def body_size_ok(self, size: int) -> bool:
        return size <= self.max_body_bytes

    def json_depth_ok(self, payload: Any) -> bool:
        return json_depth(payload) <= self.max_json_depth
