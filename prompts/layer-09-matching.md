# LEDGER — Layer 09: Matching

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement deterministic matching rules, rule/version attribution, ambiguity detection, and 1:1 matching constraints.

## Scope

Implement only the responsibilities belonging to **Matching**.

You may add implementation code, tests, minimal supporting abstractions, and documentation directly required by this layer.

## Forbidden Changes

Do not:

- redesign `Architecture.md`,
- silently change domain semantics,
- implement future layers,
- bypass invariants,
- change source-of-truth ownership,
- add speculative distributed infrastructure,
- add unrelated dependencies,
- weaken tests to make the implementation pass.

If the architecture is insufficient, STOP and report the contradiction.

## Dependencies

Layer 8 candidate sets and Layer 7 identities. Use immutable policy `standard_v1`, rules M-001/M-002, and conflict algorithm in `Architecture.md` §§25-26.

## Allowed Changes

Implement deterministic rule evaluation, ambiguity classification, proposal construction, and global 1:1 conflict detection. Do not create resolutions or mutate historical decisions.

## Contracts

M-001 exact non-empty transaction reference has priority 100; M-002 exact amount/currency and date difference <=2 days has priority 50. Higher-priority ambiguity cannot be overridden. Any proposal graph conflict classifies the whole component `DUPLICATE` with no automatic winner.

## Invariants Owned/Enforced

L-INV-006, L-INV-007, L-INV-009, and L-INV-012.

## Verification

V2/V3/V4 tests must cover unique matches, mismatches, ambiguity, no candidates, rule conflicts, proposal conflicts, process-order independence, and complete evidence.

## Evidence

Record policy/rule versions, ordered candidates, comparisons, proposals, conflict components, and decision timestamps.

## Exit Condition

Exit only when matching never selects arbitrarily and every proposal is reproducible from the persisted candidate set.

## Required Process

### 1. Inspect

Inspect the repository, `AGENTS.md`, `Architecture.md`, existing implementation, and current layer state.

### 2. Plan

State:

- files likely to change,
- contracts being implemented,
- dependencies on earlier layers,
- risks,
- verification approach.

### 3. Implement

Implement the smallest coherent solution satisfying this layer.

### 4. Verify

Run all relevant checks available:

- formatting
- lint/static checks
- type checks
- unit tests
- integration tests
- deterministic/idempotency tests where applicable

### 5. Architectural Verification

Confirm:

- state ownership is correct,
- dependency direction remains correct,
- no future-layer responsibility leaked in,
- invariants remain enforceable,
- failure behavior is not accidentally undefined.

### 6. Report

Return:

```text
Layer:
Status:

Implemented:
- ...

Files changed:
- ...

Tests/checks:
- ...

Architecture verification:
- ...

Evidence:
- ...

Limitations:
- ...

Remaining work:
- ...
```

## Acceptance Criteria

- Matching is reproducible and never silently forces an ambiguous match.
- M-001/M-002 and conflict-graph contracts from the Contracts section are explicit.
- Rule, ambiguity, conflict, and replay tests pass.
- L-INV-006, L-INV-007, L-INV-009, and L-INV-012 are evidenced.
- No known architectural contradiction remains.
- The repository remains understandable to another engineer or agent.

## Stop Conditions

STOP rather than guessing if:

- a required field/state is undefined,
- source-of-truth ownership is unclear,
- a state transition is ambiguous,
- a new domain concept is required,
- an invariant conflicts with implementation,
- a dependency requires an architectural decision,
- the layer requires changing an earlier contract.

## Final Instruction

Implement this layer only.

Verify it.

Report evidence.

**Do not continue to the next layer.**
