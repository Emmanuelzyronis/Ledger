# LEDGER — Layer 15: Product Proof

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Build the reproducible end-to-end demonstration using deliberately imperfect data, showing reconciliation, ambiguity, discrepancy/resolution, audit evidence, and measurable verification.

## Scope

Implement only the responsibilities belonging to **Product Proof**.

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

Layers 1-14. Use the deterministic proof dataset and evidence requirements in `Architecture.md` §§47-48.

## Allowed Changes

Add only reproducible demonstration fixtures, runners, and proof documentation. Do not change business semantics to make the demonstration pass.

## Contracts

Demonstrate A001/B991 and A002/B992 as `MATCHED`, A003 as `UNMATCHED_A`, A004 as `AMBIGUOUS`, A005 as `INVALID`, B993 as `UNMATCHED_B`, and an added A006/B996 reference match with amount difference as `MISMATCHED`. Include duplicate submission, business duplicate, late arrival, correction, restart, resolution, audit, and telemetry evidence.

## Invariants Owned/Enforced

Verify all L-INV-001 through L-INV-012 end to end.

## Verification

Run V5 against fixed input manifests and compare every expected identity, candidate list, rule, outcome, version, audit event, counter, and correlation ID. The proof must be repeatable without implicit ordering.

## Evidence

Publish source fixtures, checksums, pipeline output, reconciliation records, discrepancy/resolution history, audit trail, failure/recovery output, metrics, and benchmark references.

## Exit Condition

Exit only when another engineer can reproduce the complete proof from repository artifacts and obtain the same deterministic results.

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

- A clean product proof demonstrates the mission end-to-end and can be reproduced by another engineer.
- The fixed proof dataset, expected outcomes, evidence fields, and replay contract are explicit.
- V5 produces the expected deterministic output.
- L-INV-001 through L-INV-012 are evidenced end to end.
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
