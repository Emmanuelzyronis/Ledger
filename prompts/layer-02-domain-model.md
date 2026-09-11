# LEDGER — Layer 02: Domain Model

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement the canonical domain vocabulary, entities/value objects, outcomes, and state semantics required by Architecture.md. Keep infrastructure out of the domain.

## Scope

Implement only the responsibilities belonging to **Domain Model**.

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

Layer 1 foundation. Use canonical fields and source-independent semantics from `Architecture.md` §§21-24; do not define persistence details.

## Allowed Changes

Add domain entities/value objects, enums, pure transition guards, and domain tests. Keep concrete storage, HTTP, authentication, logging, and metrics out of the domain.

## Contracts

Implement the canonical transaction contract (§21), all reconciliation outcomes (§15), batch/attempt/reconciliation/discrepancy transition tables (§§23-24), and current-state/version semantics (§§27-28).

## Invariants Owned/Enforced

L-INV-002, L-INV-003, L-INV-007, L-INV-009, L-INV-011, and L-INV-012 at the domain boundary.

## Verification

V2 unit tests must cover value validation, every legal/illegal transition, all outcomes, version supersession, and deterministic serialization inputs.

## Evidence

Provide domain API documentation, transition tables exercised by tests, and deterministic test output.

## Exit Condition

Exit only when domain objects and guards compile independently of infrastructure and every state/outcome has a legal path.

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

- Domain objects and state rules are independently testable and infrastructure-independent.
- Canonical fields, outcomes, transitions, and version semantics from the Contracts section are explicit.
- V2 transition/value-object tests pass.
- L-INV-002, L-INV-003, L-INV-007, L-INV-009, L-INV-011, and L-INV-012 are covered by evidence.
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
