"""Representative staging dataset: the proven portfolio, scaled by shards.

Rather than invent new matching semantics for a load test, this module repeats
the Layer 15 portfolio fixture (whose outcomes are proven in
`product_proof/dataset.py` and `evidence/product-proof.json`) as independent
*shards*. Shard `s` is a structure-preserving relabeling of the portfolio:

* amounts are shifted by `1000 * s`, so the amount sets of two shards are
  disjoint (amount equality is what candidate eligibility requires);
* dates are shifted by `3 * s` days, which preserves each record's offset from
  its counterpart and keeps the within-shard temporal structure isomorphic;
* references and record ids are suffixed with the shard, so reference-keyed
  candidates cannot cross shards either.

Amount equality, currency equality, direction, reference equality, and
fingerprint structure are all preserved inside a shard, and no candidate can
span two shards, so each shard must reproduce exactly the portfolio's outcome
distribution. That is what makes the scaled dataset *representative* rather
than merely large.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from product_proof import dataset as portfolio
from product_proof.dataset import EXPECTED_PORTFOLIO_OUTCOMES  # noqa: F401 - re-exported for the proof

# Outcomes the portfolio produces per shard, derived from its 17 records.
EXPECTED_PER_SHARD: dict[str, int] = {
    "MATCHED": 4,
    "MISMATCHED": 4,
    "AMBIGUOUS": 3,
    "DUPLICATE": 3,
    "UNMATCHED_A": 1,
    "UNMATCHED_B": 1,
    "INVALID": 1,
}
RECORDS_PER_SHARD = sum(EXPECTED_PER_SHARD.values())  # 17
AMOUNT_STRIDE = Decimal("1000")
DATE_STRIDE_DAYS = 3


def _shift_amount(value: str, shard: int) -> str:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        # A deliberately malformed field stays malformed; shifting it would
        # change which validation rule it exercises.
        return value
    if amount == amount.quantize(Decimal("0.01")):
        shifted = amount + AMOUNT_STRIDE * shard
        return f"{shifted:.2f}"
    return value


def _shift_date(value: str, shard: int) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return (parsed + timedelta(days=DATE_STRIDE_DAYS * shard)).isoformat()


def shard_payloads(shard: int) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (source_a, source_b) payloads for one shard, keyed by record id."""
    suffix = f"-S{shard}"
    source_a: dict[str, dict[str, Any]] = {}
    for record_id, payload in portfolio.PORTFOLIO_A.items():
        shifted = dict(payload)
        shifted["record_id"] = f"{record_id}{suffix}"
        shifted["amount"] = _shift_amount(payload["amount"], shard)
        shifted["occurred_at"] = _shift_date(payload["occurred_at"], shard)
        if payload.get("transaction_reference"):
            shifted["transaction_reference"] = f"{payload['transaction_reference']}{suffix}"
        source_a[shifted["record_id"]] = shifted
    source_b: dict[str, dict[str, Any]] = {}
    for record_id, payload in portfolio.PORTFOLIO_B.items():
        shifted = dict(payload)
        shifted["id"] = f"{record_id}{suffix}"
        shifted["value"] = _shift_amount(payload["value"], shard)
        shifted["posted"] = _shift_date(payload["posted"], shard)
        if payload.get("reference"):
            shifted["reference"] = f"{payload['reference']}{suffix}"
        source_b[shifted["id"]] = shifted
    return source_a, source_b


def scaled_payloads(shards: int) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return the concatenation of `shards` independent portfolio shards."""
    source_a: dict[str, dict[str, Any]] = {}
    source_b: dict[str, dict[str, Any]] = {}
    for shard in range(shards):
        shard_a, shard_b = shard_payloads(shard)
        source_a.update(shard_a)
        source_b.update(shard_b)
    return source_a, source_b


def expected_outcomes(shards: int) -> dict[str, int]:
    """Record-level outcome counts the engine must produce for `shards`."""
    return {outcome: count * shards for outcome, count in EXPECTED_PER_SHARD.items()}


def expected_records_a(shards: int) -> int:
    return len(portfolio.PORTFOLIO_A) * shards


def expected_records_b(shards: int) -> int:
    return len(portfolio.PORTFOLIO_B) * shards
