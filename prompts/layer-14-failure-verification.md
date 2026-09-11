# LEDGER — Layer 14: Failure Verification

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Exercise restart, duplicate, partial failure, dependency failure, late-arrival, correction, and recovery scenarios. Turn discovered failures into regression tests.

## Scope

Implement only the responsibilities belonging to **Failure Verification**.

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

Layers 1-13. Use the complete state, retry, correction, late-arrival, transaction, and audit contracts in `Architecture.md` §§23-32 and security/observability ownership §§35-36.

## Allowed Changes

Add failure-injection scenarios and regression tests. Fixes may be made only in the previously assigned layer and must preserve its contract; do not redesign architecture here.

## Contracts

Exercise duplicate submission, malformed input, restart, timeout/cancellation, database interruption, partial batch failure, late arrival, correction, ambiguity, business duplicates, matching failure, security failure, and telemetry failure according to the explicit transitions.

## Invariants Owned/Enforced

Verify all L-INV-001 through L-INV-012 under failure and retry conditions.

## Verification

V4 tests must demonstrate atomicity, no duplicate business effects, explicit terminal states, deterministic replay, preserved history, authorization failures, redaction, and recovery evidence.

## Evidence

Record injected fault, attempt ID, batch/reconciliation IDs, before/after authoritative state, audit events, and recovery result.

## Exit Condition

Exit only when every required failure scenario has an automated or explicitly justified reproducible result.

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

- Important failure paths are demonstrated with evidence and automated where practical.
- Failure-injection scenarios map explicitly to the state, retry, security, and telemetry contracts.
- V4 recovery tests pass with before/after evidence.
- L-INV-001 through L-INV-012 are covered for applicable failure paths.
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
