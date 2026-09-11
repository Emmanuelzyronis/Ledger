"""Secure runtime configuration boundaries for LEDGER foundation code."""

from __future__ import annotations

from dataclasses import dataclass
import os
from collections.abc import Mapping


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid or a required secret is absent."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret runtime settings with explicit, safe defaults."""

    environment: str = "development"
    log_level: str = "INFO"
    telemetry_enabled: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        environment = values.get("LEDGER_ENV", "development").strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ConfigError("LEDGER_ENV must be development, test, or production")

        log_level = values.get("LEDGER_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("LEDGER_LOG_LEVEL is not a supported log level")

        telemetry = values.get("LEDGER_TELEMETRY_ENABLED", "true").strip().lower()
        if telemetry not in {"true", "false"}:
            raise ConfigError("LEDGER_TELEMETRY_ENABLED must be true or false")

        return cls(
            environment=environment,
            log_level=log_level,
            telemetry_enabled=telemetry == "true",
        )


def load_secret(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Load a secret from the runtime environment without providing a source-code default."""

    if not name or not name.isidentifier():
        raise ConfigError("secret name must be a valid environment variable name")
    values = os.environ if environ is None else environ
    value = values.get(name)
    if value is None or not value:
        raise ConfigError(f"required secret {name!r} is not configured")
    return value
