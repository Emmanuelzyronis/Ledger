"""Layer 8 bounded, deterministic candidate generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import hashlib
from typing import Iterable

from .domain import CanonicalTransaction, MatchCandidate
from .identity import canonical_json
from .observability import CorrelationContext, TelemetryEvent, TelemetrySink
from .persistence import LedgerDatabase


CANDIDATE_VERSION = "candidate_v1"
REFERENCE_INDEX = "IDX-REFERENCE"
AMOUNT_DATE_INDEX = "IDX-AMOUNT-CURRENCY-DATE"


class CandidateGenerationService:
    def __init__(self, database: LedgerDatabase, telemetry: TelemetrySink | None = None, *, candidate_version: str = CANDIDATE_VERSION) -> None:
        self.database, self.telemetry, self.candidate_version = database, telemetry, candidate_version

    def generate_for(self, canonical_id: str) -> list[MatchCandidate]:
        target = self.database.canonical_transactions.get(canonical_id)
        if target is None:
            raise ValueError("canonical transaction does not exist")
        counterparties = [item for item in self.database.canonical_transactions.list_all() if self._side(item) != self._side(target)]
        candidates = self._generate(target, counterparties)
        self._persist(candidates)
        self._emit(target, len(candidates))
        return candidates

    def generate_candidates(self, canonical_id: str | None = None) -> list[MatchCandidate]:
        return self.generate_all() if canonical_id is None else self.generate_for(canonical_id)

    def generate_all(self) -> list[MatchCandidate]:
        transactions = self.database.canonical_transactions.list_all()
        sides = {item.canonical_id: self._side(item) for item in transactions}
        by_reference: dict[tuple[str, str], list[CanonicalTransaction]] = defaultdict(list)
        by_amount_date: dict[tuple[str, Decimal, date], list[CanonicalTransaction]] = defaultdict(list)
        for item in transactions:
            if item.transaction_reference:
                by_reference[(sides[item.canonical_id], item.transaction_reference)].append(item)
            by_amount_date[(sides[item.canonical_id], item.currency, item.amount, item.occurred_at.date())].append(item)
        all_candidates: list[MatchCandidate] = []
        for target in transactions:
            if sides[target.canonical_id] != "a":
                continue
            opposite = "b" if sides[target.canonical_id] == "a" else "a"
            matched: dict[str, tuple[set[str], dict[str, object]]] = {}
            if target.transaction_reference:
                for item in by_reference[(opposite, target.transaction_reference)]:
                    matched.setdefault(item.canonical_id, (set(), {}))[0].add(REFERENCE_INDEX)
            for offset in range(-2, 3):
                day = target.occurred_at.date() + timedelta(days=offset)
                for item in by_amount_date[(opposite, target.currency, target.amount, day)]:
                    matched.setdefault(item.canonical_id, (set(), {}))[0].add(AMOUNT_DATE_INDEX)
            for counterpart_id in sorted(matched):
                indexes, _ = matched[counterpart_id]
                all_candidates.append(self._candidate(target, self.database.canonical_transactions.get(counterpart_id), indexes))
        all_candidates.sort(key=lambda item: (item.source_a_canonical_id, item.source_b_canonical_id))
        self._persist(all_candidates)
        for target in transactions:
            self._emit(target, sum(target.canonical_id in (c.source_a_canonical_id, c.source_b_canonical_id) for c in all_candidates))
        return all_candidates

    def _generate(self, target: CanonicalTransaction, counterparties: Iterable[CanonicalTransaction]) -> list[MatchCandidate]:
        by_reference: dict[str, list[CanonicalTransaction]] = defaultdict(list)
        by_amount_date: dict[tuple[str, Decimal, date], list[CanonicalTransaction]] = defaultdict(list)
        by_id: dict[str, CanonicalTransaction] = {}
        for item in counterparties:
            by_id[item.canonical_id] = item
            if item.transaction_reference:
                by_reference[item.transaction_reference].append(item)
            by_amount_date[(item.currency, item.amount, item.occurred_at.date())].append(item)
        matched: dict[str, set[str]] = defaultdict(set)
        if target.transaction_reference:
            for item in by_reference.get(target.transaction_reference, []):
                matched[item.canonical_id].add(REFERENCE_INDEX)
        for offset in range(-2, 3):
            for item in by_amount_date.get((target.currency, target.amount, target.occurred_at.date() + timedelta(days=offset)), []):
                matched[item.canonical_id].add(AMOUNT_DATE_INDEX)
        return [self._candidate(target, by_id[counterpart_id], indexes) for counterpart_id, indexes in sorted(matched.items())]

    def _candidate(self, target: CanonicalTransaction, counterpart: CanonicalTransaction | None, indexes: set[str]) -> MatchCandidate:
        if counterpart is None:
            raise ValueError("candidate counterpart does not exist")
        left, right = (target, counterpart) if self._side(target) == "a" else (counterpart, target)
        candidate_id = "candidate:" + hashlib.sha256(canonical_json([left.canonical_id, right.canonical_id, self.candidate_version])).hexdigest()
        evidence = {"candidate_version": self.candidate_version, "indexes": sorted(indexes), "source_a_date": left.occurred_at.date().isoformat(), "source_b_date": right.occurred_at.date().isoformat()}
        return MatchCandidate(candidate_id, left.canonical_id, right.canonical_id, tuple(sorted(indexes)), evidence)

    def _persist(self, candidates: list[MatchCandidate]) -> None:
        with self.database.transaction():
            for candidate in candidates:
                self.database.match_candidates.save(candidate)

    def _emit(self, target: CanonicalTransaction, count: int) -> None:
        if self.telemetry:
            raw = self.database.raw_records.get(target.raw_record_id)
            self.telemetry.emit(TelemetryEvent("ledger.candidates.generated", CorrelationContext(batch_id=raw.batch_id if raw else None, record_id=target.raw_record_id), {"canonical_transaction_id": target.canonical_id, "candidate_version": self.candidate_version, "candidate_count": count, "outcome": "GENERATED"}))

    def _side(self, transaction: CanonicalTransaction) -> str:
        raw = self.database.raw_records.get(transaction.raw_record_id)
        if raw is None:
            raise ValueError("canonical transaction lineage is missing")
        if raw.schema_version == "source_a.v1":
            return "a"
        if raw.schema_version == "source_b.v1":
            return "b"
        raise ValueError("unsupported source schema for candidate generation")


CandidateGeneration = CandidateGenerationService
CandidateGenerator = CandidateGenerationService
