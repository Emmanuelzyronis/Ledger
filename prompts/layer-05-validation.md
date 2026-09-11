# LEDGER — Layer 05: Validation

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement structural, semantic, and business validation while preserving invalid records and their evidence.

## Scope

Implement only the responsibilities belonging to **Validation**.

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

Layer 4 raw records and the two source schemas in `Architecture.md` §21.1.

## Allowed Changes

Implement structural, semantic, and business validation plus invalid-record classification/evidence. Do not normalize, identify, or match.

## Contracts

Use the validation categories in §8 and invalid semantics/counters in §22. Invalid raw records receive no canonical transaction and cannot enter matching.

## Invariants Owned/Enforced

L-INV-005 and the input-validation portions of L-INV-006.

## Verification

V2/V3 tests must cover every required/optional field, date/amount/currency formats, direction, unknown schema versions, unsupported states, and invalid-record persistence.

## Evidence

Record validation rule/version, field-level errors, raw record ID, batch counters, and `RECORD_INVALID` audit/telemetry.

## Exit Condition

Exit only when valid and invalid inputs are explicit, reproducible, and separated from normalization and matching.

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

- Valid and invalid records receive explicit classifications with tests covering important validation boundaries.
- Validation categories and invalid-record contracts from the Contracts section are explicit.
- Boundary tests for both schemas pass.
- L-INV-005 and input portions of L-INV-006 are evidenced.
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
