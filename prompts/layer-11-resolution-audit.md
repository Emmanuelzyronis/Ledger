# LEDGER — Layer 11: Resolution + Audit

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement discrepancy resolution and append-only audit evidence while preserving original decisions and historical state.

## Scope

Implement only the responsibilities belonging to **Resolution + Audit**.

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

Layer 10 reconciliation and Layer 3 persistence. Use discrepancy/resolution transitions, actor `reconciliation_operator`, audit schema, and atomicity rules in `Architecture.md` §§24, 18, 30.

## Allowed Changes

Implement immutable discrepancy resolutions, authorization checks for automatic/manual decisions, append-only audit events, and current-state derivation. Do not change raw or prior reconciliation versions.

## Contracts

Discrepancies use `OPEN`, `DEFERRED`, `RESOLVED`, `REJECTED`; resolutions are immutable entities with explicit types. Manual resolution requires `reconciliation_operator`; every transition writes one deterministic audit event transactionally.

## Invariants Owned/Enforced

L-INV-006, L-INV-007, L-INV-008, L-INV-010, and L-INV-011.

## Verification

V2/V3/V4 tests must cover authorization, automatic/manual/deferred/rejected paths, append-only enforcement, event deduplication, rollback on audit failure, and historical visibility.

## Evidence

Record discrepancy/resolution IDs, actor and reason, supersession links, audit event IDs/sequences, and atomic transaction results.

## Exit Condition

Exit only when every resolution is attributable and audit/history cannot be lost or overwritten on retry.

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

- Every resolution is attributable and historical evidence remains intact.
- Discrepancy, resolution-authority, audit, and atomicity contracts from the Contracts section are explicit.
- Authorization, append-only, retry, and rollback tests pass.
- L-INV-006, L-INV-007, L-INV-008, L-INV-010, and L-INV-011 are evidenced.
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
