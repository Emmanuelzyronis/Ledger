# LEDGER — Layer 10: Reconciliation

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement authoritative reconciliation records and explicit outcomes: MATCHED, MISMATCHED, UNMATCHED_A, UNMATCHED_B, AMBIGUOUS, DUPLICATE, INVALID.

## Scope

Implement only the responsibilities belonging to **Reconciliation**.

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

Layer 9 matching proposals and Layer 3 persistence. Use all seven outcomes, versioned reconciliation, discrepancy lifecycle, and batch counters in `Architecture.md` §§15-16, 22, 24.

## Allowed Changes

Create immutable authoritative reconciliation versions, classify outcomes, create discrepancies for mismatches/ambiguity, and update transactional batch counters. Do not apply resolutions or projections.

## Contracts

Use `MATCHED`, `MISMATCHED`, `UNMATCHED_A`, `UNMATCHED_B`, `AMBIGUOUS`, `DUPLICATE`, and `INVALID` exactly as defined. `MISMATCHED` requires a unique proposal with failed comparison; no proposal yields the side-specific unmatched outcome.

## Invariants Owned/Enforced

L-INV-005, L-INV-006, L-INV-009, and L-INV-011.

## Verification

V2/V3 tests must cover every outcome path, version supersession, counter reconciliation, atomic discrepancy creation, and illegal transition rejection.

## Evidence

Record reconciliation/version IDs, outcomes, rule/evidence payloads, discrepancy IDs, counters, and audit correlation fields.

## Exit Condition

Exit only when every product outcome has an explicit legal path and authoritative current state is derived from immutable versions.

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

- Reconciliation state is authoritative, transitions are valid, and outcomes are explainable.
- Outcome, discrepancy, version, and counter contracts from the Contracts section are explicit.
- Every outcome and illegal transition has passing tests.
- L-INV-005, L-INV-006, L-INV-009, and L-INV-011 are evidenced.
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
