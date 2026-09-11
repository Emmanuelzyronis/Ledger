"""Pure domain values and enumerations for LEDGER Layer 2."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import re
import unicodedata

from .errors import InvalidValueError


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[^\s]+$")


class Direction(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class ReconciliationOutcome(str, Enum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNMATCHED_A = "UNMATCHED_A"
    UNMATCHED_B = "UNMATCHED_B"
    AMBIGUOUS = "AMBIGUOUS"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"


class BatchState(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ProcessingAttemptState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ReconciliationState(str, Enum):
    CREATED = "CREATED"
    EVALUATING = "EVALUATING"
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNMATCHED_A = "UNMATCHED_A"
    UNMATCHED_B = "UNMATCHED_B"
    AMBIGUOUS = "AMBIGUOUS"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"
    RESOLVED = "RESOLVED"


class DiscrepancyState(str, Enum):
    OPEN = "OPEN"
    DEFERRED = "DEFERRED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class ResolutionType(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_APPROVED = "MANUAL_APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class AuditEventType(str, Enum):
    BATCH_RECEIVED = "BATCH_RECEIVED"
    BATCH_STATE_CHANGED = "BATCH_STATE_CHANGED"
    BATCH_COMPLETED = "BATCH_COMPLETED"
    SUBMISSION_DUPLICATE = "SUBMISSION_DUPLICATE"
    RECORD_INGESTED = "RECORD_INGESTED"
    RECORD_INVALID = "RECORD_INVALID"
    RECORD_VALIDATED = "RECORD_VALIDATED"
    NORMALIZATION_COMPLETED = "NORMALIZATION_COMPLETED"
    MATCH_EVALUATED = "MATCH_EVALUATED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
    RECONCILIATION_CREATED = "RECONCILIATION_CREATED"
    DISCREPANCY_CREATED = "DISCREPANCY_CREATED"
    RESOLUTION_APPLIED = "RESOLUTION_APPLIED"
    PROJECTION_REBUILT = "PROJECTION_REBUILT"


def require_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value or not _ID_RE.fullmatch(value):
        raise InvalidValueError(f"{field_name} must be a non-empty, whitespace-free string")
    return value


def normalize_text(value: str | None, field_name: str, *, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidValueError(f"{field_name} must be a string or None")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not allow_empty and not normalized:
        raise InvalidValueError(f"{field_name} must not be empty")
    return normalized


def require_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def require_amount(value: Decimal | str | int, field_name: str = "amount") -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidValueError(f"{field_name} must be a decimal value") from exc
    if not amount.is_finite():
        raise InvalidValueError(f"{field_name} must be finite")
    exponent = amount.as_tuple().exponent
    fractional_digits = -exponent if exponent < 0 else 0
    if fractional_digits > 4:
        raise InvalidValueError(f"{field_name} may have at most 4 fractional digits")
    integer_digits = 1 if amount.is_zero() else max(amount.copy_abs().adjusted() + 1, 0)
    if integer_digits > 16 or integer_digits + fractional_digits > 20:
        raise InvalidValueError(f"{field_name} exceeds Decimal(20,4) precision")
    return amount.quantize(Decimal("0.0001"))


def require_currency(value: str) -> str:
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isupper() or not value.isalpha():
        raise InvalidValueError("currency must be an uppercase three-letter ISO-4217 code")
    return value


def require_fingerprint(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise InvalidValueError(f"{field_name} must be a lowercase SHA-256 hex string")
    return value


def freeze_mapping(value: Mapping[str, object] | None) -> Mapping[str, object]:
    """Copy a mapping into an immutable, deterministically ordered mapping."""

    from types import MappingProxyType

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise InvalidValueError("mapping value expected")
    copied = {str(key): _freeze_value(value[key]) for key in sorted(value, key=str)}
    return MappingProxyType(copied)


def _freeze_value(value: object) -> object:
    from types import MappingProxyType

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(value[key]) for key in sorted(value, key=str)})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value
