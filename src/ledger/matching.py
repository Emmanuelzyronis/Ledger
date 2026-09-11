"""Layer 9 deterministic matching over persisted candidate pairs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Iterable

from .domain import (
    AuditEvent,
    AuditEventType,
    CanonicalTransaction,
    MatchCandidate,
    Reconciliation,
    ReconciliationOutcome,
    ReconciliationState,
)
from .identity import canonical_json
from .persistence import LedgerDatabase
from .reconciliation import ReconciliationService


MATCHING_RULE_VERSION = "standard_v1"
MATCHING_STAGE_VERSION = "matching_v1"
M001 = "M-001"
M002 = "M-002"


@dataclass(frozen=True, slots=True)
class MatchDecision:
    reconciliation: Reconciliation
    outcome: ReconciliationOutcome


class MatchingService:
    """Evaluate only the candidate snapshot; candidate generation stays upstream."""

    def __init__(self, database: LedgerDatabase, *, rule_version: str = MATCHING_RULE_VERSION) -> None:
        self.database = database
        self.rule_version = rule_version
        self.reconciliation = ReconciliationService(database)

    def evaluate(self, candidates: Iterable[MatchCandidate] | None = None, *, evaluated_at: datetime | None = None) -> list[MatchDecision]:
        timestamp = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        snapshot = sorted(list(candidates) if candidates is not None else self.database.match_candidates.list_all(),
                          key=lambda item: (item.source_a_canonical_id, item.source_b_canonical_id, item.candidate_id))
        transactions = {item.canonical_id: item for item in self.database.canonical_transactions.list_all()}
        if any(item.source_a_canonical_id not in transactions or item.source_b_canonical_id not in transactions for item in snapshot):
            raise ValueError("candidate snapshot references a missing canonical transaction")

        by_a: dict[str, list[MatchCandidate]] = {}
        by_b: dict[str, list[MatchCandidate]] = {}
        for candidate in snapshot:
            by_a.setdefault(candidate.source_a_canonical_id, []).append(candidate)
            by_b.setdefault(candidate.source_b_canonical_id, []).append(candidate)

        proposals: dict[str, str] = {}
        proposal_rule: dict[tuple[str, str], str] = {}
        ambiguous: set[str] = set()
        evaluations: dict[str, dict[str, object]] = {}
        for canonical_id, side_candidates in ((key, value) for key, value in sorted(by_a.items())):
            result = self._select(canonical_id, side_candidates, transactions, "A")
            evaluations[canonical_id] = result[2]
            if result[0] == "AMBIGUOUS":
                ambiguous.add(canonical_id)
            elif result[0] == "PROPOSAL":
                proposals[canonical_id] = result[1]
                proposal_rule[(canonical_id, result[1])] = result[3]
        for canonical_id, side_candidates in ((key, value) for key, value in sorted(by_b.items())):
            result = self._select(canonical_id, side_candidates, transactions, "B")
            evaluations.setdefault(canonical_id, result[2])
            if result[0] == "AMBIGUOUS":
                ambiguous.add(canonical_id)
            elif result[0] == "PROPOSAL":
                proposals[canonical_id] = result[1]
                proposal_rule[(result[1], canonical_id)] = result[3]

        # A proposal is valid only when both sides independently selected it.
        mutual = {(a, b) for a, b in proposals.items() if a in by_a and proposals.get(b) == a and a not in ambiguous and b not in ambiguous}
        proposal_edges = set()
        for source, target in proposals.items():
            if source in by_a:
                if source not in ambiguous and target not in ambiguous:
                    proposal_edges.add((source, target))
            else:
                if source not in ambiguous and target not in ambiguous:
                    proposal_edges.add((target, source))
        conflict_components = self._conflicts(proposal_edges)
        decisions: list[MatchDecision] = []
        decided: set[str] = set()
        for component in sorted(conflict_components, key=lambda item: tuple(sorted(item))):
            decisions.extend(self._persist_component(component, mutual, snapshot, transactions, evaluations, timestamp, ReconciliationOutcome.DUPLICATE))
            decided.update(component)
        for canonical_id in sorted(transactions):
            if canonical_id in decided:
                continue
            if canonical_id in ambiguous:
                outcome, counterpart = ReconciliationOutcome.AMBIGUOUS, None
            elif canonical_id in proposals and any(canonical_id in pair for pair in mutual):
                counterpart = next((b if a == canonical_id else a for a, b in mutual if canonical_id in (a, b)), None)
                left, right = transactions[canonical_id], transactions[counterpart] if counterpart else None
                outcome = self._pair_outcome(left, right)
            else:
                counterpart = None
                outcome = ReconciliationOutcome.UNMATCHED_A if self._side(transactions[canonical_id]) == "A" else ReconciliationOutcome.UNMATCHED_B
            decisions.append(self._persist_decision(canonical_id, counterpart, outcome, snapshot, evaluations, proposal_rule, transactions, timestamp))
            decided.add(canonical_id)
            if counterpart:
                decided.add(counterpart)
        return decisions

    def _select(self, canonical_id: str, candidates: list[MatchCandidate], transactions: dict[str, CanonicalTransaction], side: str):
        ordered = sorted(candidates, key=lambda item: (item.source_a_canonical_id, item.source_b_canonical_id, item.candidate_id))
        checks: list[dict[str, object]] = []
        for rule in (M001, M002):
            matches = []
            for candidate in ordered:
                counterpart_id = candidate.source_b_canonical_id if side == "A" else candidate.source_a_canonical_id
                left = transactions[canonical_id]
                right = transactions[counterpart_id]
                matched = (rule == M001 and bool(left.transaction_reference) and left.transaction_reference == right.transaction_reference) or (rule == M002 and left.amount == right.amount and left.currency == right.currency and abs((left.occurred_at.date() - right.occurred_at.date()).days) <= 2)
                checks.append({"candidate_id": candidate.candidate_id, "rule_id": rule, "matched": matched})
                if matched:
                    matches.append(counterpart_id)
            if matches:
                unique = sorted(set(matches))
                evidence = {"rule_version": self.rule_version, "canonical_id": canonical_id, "side": side, "ordered_candidates": [c.candidate_id for c in ordered], "comparisons": checks, "selected_rule": rule, "selected_counterparts": unique}
                if len(unique) == 1:
                    return "PROPOSAL", unique[0], evidence, rule
                return "AMBIGUOUS", "", evidence, rule
        return "NONE", "", {"rule_version": self.rule_version, "canonical_id": canonical_id, "side": side, "ordered_candidates": [c.candidate_id for c in ordered], "comparisons": checks, "selected_rule": None}, ""

    def _conflicts(self, mutual: set[tuple[str, str]]) -> list[set[str]]:
        graph: dict[str, set[str]] = {}
        for a, b in mutual:
            graph.setdefault(a, set()).add(b); graph.setdefault(b, set()).add(a)
        seen: set[str] = set(); components: list[set[str]] = []
        for node in sorted(graph):
            if node in seen: continue
            stack, component = [node], set()
            while stack:
                current = stack.pop()
                if current in seen: continue
                seen.add(current); component.add(current); stack.extend(graph[current] - seen)
            if len(component) > 2 or any(len(graph[item]) > 1 for item in component): components.append(component)
        return components

    def _persist_component(self, component, mutual, snapshot, transactions, evaluations, timestamp, outcome):
        result = []
        for canonical_id in sorted(component):
            result.append(self._persist_decision(canonical_id, None, outcome, snapshot, evaluations, {}, transactions, timestamp))
        return result

    def _persist_decision(self, canonical_id, counterpart, outcome, snapshot, evaluations, proposal_rule, transactions, timestamp):
        left = transactions[canonical_id]
        a_id, b_id = (canonical_id, counterpart) if self._side(left) == "A" else (counterpart, canonical_id)
        batch_id = self.database.raw_records.get(left.raw_record_id).batch_id  # type: ignore[union-attr]
        evidence = {"rule_version": self.rule_version, "evaluated_at": timestamp.isoformat(), "candidate_order": [c.candidate_id for c in snapshot if canonical_id in (c.source_a_canonical_id, c.source_b_canonical_id)], "evaluation": evaluations.get(canonical_id, {}), "outcome": outcome.value}
        if counterpart:
            evidence["counterpart_canonical_id"] = counterpart
            evidence["selected_rule"] = proposal_rule.get((a_id, b_id))
        persisted = self.reconciliation.persist_decision(
            batch_id=batch_id, source_a_record_id=a_id, source_b_record_id=b_id,
            outcome=outcome, evidence=evidence, rule_version=self.rule_version, evaluated_at=timestamp,
        )
        return MatchDecision(persisted, outcome)

    def _pair_outcome(self, left, right):
        return ReconciliationOutcome.MATCHED if left.amount == right.amount and left.currency == right.currency and left.direction == right.direction else ReconciliationOutcome.MISMATCHED

    def _side(self, transaction):
        raw = self.database.raw_records.get(transaction.raw_record_id)
        return "A" if raw and raw.schema_version == "source_a.v1" else "B"


Matching = MatchingService
