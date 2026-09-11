"""Deterministic Layer 15 product-proof fixture manifests.

The fixtures mirror Architecture.md section 47. Every payload is fixed so the
suite is reproducible: the same payloads, services, versions, and timestamps
must produce the same authoritative state and the same evidence signature.

Schema keys
-----------
source_a.v1: record_id, occurred_at, amount, currency, direction,
              account_reference, transaction_reference, description,
              transaction_type
source_b.v1: id, posted, value, ccy, side, account_ref, reference, memo, type
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from ledger.identity import canonical_json

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
NORMALIZATION_VERSION = "canonical_v2"
VALIDATION_VERSION = "validation_v1"
RULE_VERSION = "standard_v1"

# The canonical portfolio dataset. Expected behavior is documented in
# Architecture.md section 47 plus the deterministic engine semantics:
#   A001 <-> B991        MATCHED (M-001 reference match)
#   A002 <-> B992        MATCHED (M-001 reference match)
#   A003                 UNMATCHED_A (no eligible counterpart)
#   A004 / B994 / B995   AMBIGUOUS (same amount/currency within the date window)
#   A005                 INVALID (validation failure, raw-only reconciliation)
#   A006 <-> B996        MISMATCHED (M-001 reference match, amount differs)
#   A007 <-> B997        MISMATCHED (M-001 reference match, direction differs)
#   B993                 UNMATCHED_B (no eligible counterpart)
#   D-A1 / D-A2 / D-B1   DUPLICATE (many-to-one/one-to-many proposal conflict)
PORTFOLIO_A: dict[str, Mapping[str, str]] = {
    "A001": {"record_id": "A001", "occurred_at": "2026-09-01", "amount": "100.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "TX-1001"},
    "A002": {"record_id": "A002", "occurred_at": "2026-09-02", "amount": "250.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "TX-1002"},
    "A003": {"record_id": "A003", "occurred_at": "2026-09-03", "amount": "500.00", "currency": "USD",
             "direction": "CREDIT"},
    "A004": {"record_id": "A004", "occurred_at": "2026-09-03", "amount": "100.00", "currency": "USD",
             "direction": "CREDIT"},
    "A005": {"record_id": "A005", "occurred_at": "2026-09-03", "amount": "100.00x", "currency": "USD",
             "direction": "CREDIT"},
    "A006": {"record_id": "A006", "occurred_at": "2026-09-04", "amount": "600.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "TX-1006"},
    "A007": {"record_id": "A007", "occurred_at": "2026-09-06", "amount": "800.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "TX-1007"},
    "D-A1": {"record_id": "D-A1", "occurred_at": "2026-09-05", "amount": "300.00", "currency": "USD",
             "direction": "CREDIT"},
    "D-A2": {"record_id": "D-A2", "occurred_at": "2026-09-05", "amount": "301.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "DUP-9"},
}

PORTFOLIO_B: dict[str, Mapping[str, str]] = {
    "B991": {"id": "B991", "posted": "2026-09-01", "value": "100.00", "ccy": "USD", "side": "CREDIT",
             "reference": "TX-1001"},
    "B992": {"id": "B992", "posted": "2026-09-02", "value": "250.00", "ccy": "USD", "side": "CREDIT",
             "reference": "TX-1002"},
    "B993": {"id": "B993", "posted": "2026-09-03", "value": "700.00", "ccy": "USD", "side": "CREDIT"},
    "B994": {"id": "B994", "posted": "2026-09-03", "value": "100.00", "ccy": "USD", "side": "CREDIT"},
    "B995": {"id": "B995", "posted": "2026-09-03", "value": "100.00", "ccy": "USD", "side": "CREDIT"},
    "B996": {"id": "B996", "posted": "2026-09-04", "value": "700.00", "ccy": "USD", "side": "CREDIT",
             "reference": "TX-1006"},
    "B997": {"id": "B997", "posted": "2026-09-06", "value": "800.00", "ccy": "USD", "side": "DEBIT",
             "reference": "TX-1007"},
    "D-B1": {"id": "D-B1", "posted": "2026-09-05", "value": "300.00", "ccy": "USD", "side": "CREDIT",
             "reference": "DUP-9"},
}

# Late-arriving counterpart for A003: arrives only after the first evaluation.
LATE_B: dict[str, Mapping[str, str]] = {
    "B-998": {"id": "B-998", "posted": "2026-09-03", "value": "500.00", "ccy": "USD", "side": "CREDIT"},
}

# Correction scenario: P-1 is corrected (same source-native id, new payload)
# after its first evaluation. Q-1 is the original counterpart.
CORRECTION_A: dict[str, Mapping[str, str]] = {
    "P-1": {"record_id": "P-1", "occurred_at": "2026-09-10", "amount": "120.00", "currency": "USD",
            "direction": "CREDIT", "transaction_reference": "CORR-1"},
}
CORRECTION_B: dict[str, Mapping[str, str]] = {
    "Q-1": {"id": "Q-1", "posted": "2026-09-10", "value": "120.00", "ccy": "USD", "side": "CREDIT",
            "reference": "CORR-1"},
}
CORRECTED_P1_PAYLOAD: Mapping[str, str] = {
    "record_id": "P-1", "occurred_at": "2026-09-10", "amount": "125.00", "currency": "USD",
    "direction": "CREDIT", "transaction_reference": "CORR-1",
}

# Restart scenario: two clean matched pairs persisted to a real file.
RESTART_A: dict[str, Mapping[str, str]] = {
    "R-A1": {"record_id": "R-A1", "occurred_at": "2026-09-12", "amount": "10.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "R-REF-1"},
    "R-A2": {"record_id": "R-A2", "occurred_at": "2026-09-13", "amount": "20.00", "currency": "USD",
             "direction": "CREDIT", "transaction_reference": "R-REF-2"},
}
RESTART_B: dict[str, Mapping[str, str]] = {
    "R-B1": {"id": "R-B1", "posted": "2026-09-12", "value": "10.00", "ccy": "USD", "side": "CREDIT",
             "reference": "R-REF-1"},
    "R-B2": {"id": "R-B2", "posted": "2026-09-13", "value": "20.00", "ccy": "USD", "side": "CREDIT",
             "reference": "R-REF-2"},
}

# Expected terminal outcomes for every portfolio record with a canonical or
# raw-only reconciliation. Values must match the real, deterministic engine.
EXPECTED_PORTFOLIO_OUTCOMES: dict[str, str] = {
    "A001": "MATCHED",
    "A002": "MATCHED",
    "A003": "UNMATCHED_A",
    "A004": "AMBIGUOUS",
    "A005": "INVALID",
    "A006": "MISMATCHED",
    "A007": "MISMATCHED",
    "B991": "MATCHED",
    "B992": "MATCHED",
    "B993": "UNMATCHED_B",
    "B994": "AMBIGUOUS",
    "B995": "AMBIGUOUS",
    "B996": "MISMATCHED",
    "B997": "MISMATCHED",
    "D-A1": "DUPLICATE",
    "D-A2": "DUPLICATE",
    "D-B1": "DUPLICATE",
}

# Records in EXPECTED_PORTFOLIO_OUTCOMES that are validation-invalid and are
# therefore represented by raw-only INVALID reconciliations (no canonical row).
INVALID_RECORD_IDS = ("A005",)

# Which records belong to which source.
A_RECORD_IDS: tuple[str, ...] = tuple(
    record_id for record_id, payload in PORTFOLIO_A.items()
)
B_RECORD_IDS: tuple[str, ...] = tuple(
    record_id for record_id, payload in PORTFOLIO_B.items()
)

# Expected resolution workflow on the portfolio discrepancies.
# Each entry selects one discrepancy by the reconciliation outcome and gives the
# resolution type and actor. B995 is intentionally left OPEN as residual work.
EXPECTED_RESOLUTIONS: tuple[dict[str, str], ...] = (
    {"reconciliation_outcome": "AMBIGUOUS", "resolution_type": "AUTOMATIC", "actor": "system",
     "rule_version": RULE_VERSION, "reason": "policy: accepted ambiguity under standard_v1"},
    {"reconciliation_outcome": "MISMATCHED", "resolution_type": "MANUAL_APPROVED", "actor": "reconciliation_operator",
     "rule_version": None, "reason": "reference verified; amount variance accepted"},
    {"reconciliation_outcome": "MISMATCHED", "resolution_type": "DEFERRED", "actor": "reconciliation_operator",
     "rule_version": None, "reason": "awaiting counterparty statement"},
    {"reconciliation_outcome": "AMBIGUOUS", "resolution_type": "REJECTED", "actor": "reconciliation_operator",
     "rule_version": None, "reason": "insufficient evidence to resolve"},
)
OPEN_RESOLUTION_OUTCOME = "AMBIGUOUS"


def payload_checksum(payloads: Mapping[str, Mapping[str, Any]]) -> str:
    """Return the manifest SHA-256 used to pin fixtures in evidence."""
    return hashlib.sha256(canonical_json({str(k): dict(v) for k, v in sorted(payloads.items(), key=lambda item: str(item[0]))})).hexdigest()


def manifest_sha256() -> str:
    """Checksum of every fixture used by the product-proof suite."""
    parts = {
        "portfolio_a": dict(PORTFOLIO_A),
        "portfolio_b": dict(PORTFOLIO_B),
        "late_b": dict(LATE_B),
        "correction_a": dict(CORRECTION_A),
        "correction_b": dict(CORRECTION_B),
        "corrected_p1": dict(CORRECTED_P1_PAYLOAD),
        "restart_a": dict(RESTART_A),
        "restart_b": dict(RESTART_B),
    }
    return payload_checksum(parts)


def now() -> datetime:
    """Fixed wall-clock for every runner-controlled timestamp."""
    return NOW
