import unittest

from ledger import __version__
from ledger.config import ConfigError, Settings, load_secret
from ledger.observability import (
    CorrelationContext,
    InMemoryTelemetrySink,
    TelemetryEvent,
)


class FoundationTests(unittest.TestCase):
    def test_package_exposes_foundation_version(self) -> None:
        self.assertEqual(__version__, "0.1.0")

    def test_settings_have_secure_explicit_defaults(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.log_level, "INFO")
        self.assertTrue(settings.telemetry_enabled)

    def test_settings_reject_invalid_values(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env({"LEDGER_ENV": "unknown"})
        with self.assertRaises(ConfigError):
            Settings.from_env({"LEDGER_TELEMETRY_ENABLED": "yes"})

    def test_secrets_are_runtime_only(self) -> None:
        self.assertEqual(load_secret("LEDGER_API_TOKEN", {"LEDGER_API_TOKEN": "runtime"}), "runtime")
        with self.assertRaises(ConfigError):
            load_secret("LEDGER_API_TOKEN", {})

    def test_telemetry_preserves_correlation_and_redacts_sensitive_attributes(self) -> None:
        sink = InMemoryTelemetrySink()
        sink.emit(
            TelemetryEvent(
                name="foundation.check",
                context=CorrelationContext(batch_id="batch-1", attempt_id="attempt-1"),
                attributes={
                    "records_seen": 2,
                    "api_token": "do-not-log",
                    "nested": {"description": "sensitive"},
                },
            )
        )
        event = sink.events[0]
        self.assertEqual(event["context"], {"batch_id": "batch-1", "attempt_id": "attempt-1"})
        self.assertEqual(event["attributes"]["records_seen"], 2)
        self.assertEqual(event["attributes"]["api_token"], "[REDACTED]")
        self.assertEqual(event["attributes"]["nested"]["description"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
