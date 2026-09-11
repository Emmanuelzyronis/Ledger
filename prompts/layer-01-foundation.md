# LEDGER — Layer 01: Foundation

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Establish the repository, tooling, configuration boundaries, test infrastructure, and minimal project skeleton. Do not implement reconciliation behavior.

## Scope

Implement only the responsibilities belonging to **Foundation**.

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

None. Read `Architecture.md` §§6, 33, 35-36, 43-46 before selecting tooling.

## Allowed Changes

Create only repository structure, configuration boundaries, test/verification runners, secure-default configuration, and telemetry interfaces. Do not choose unresolved business semantics.

## Contracts

The project must use the modular-monolith and relational-authority boundaries. Configuration must keep secrets outside source control, and the telemetry interface must support the correlation IDs and redaction rules in `Architecture.md` §§35-36.

## Invariants Owned/Enforced

No business invariant is implemented here. Foundation must preserve the enforcement and verification boundaries for all L-INV identifiers and must not introduce a path that bypasses them.

## Verification

Run V1 static checks and prove configuration/test/telemetry entry points are reproducible. Record architecture-boundary checks; do not claim domain-invariant coverage yet.

## Evidence

Record repository tree, configuration/secrets checks, test-runner invocation, and telemetry/redaction contract evidence.

## Exit Condition

Exit only when the skeleton runs, secure defaults are explicit, and later layers can be added without changing architecture contracts.

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

- The project runs cleanly, tests execute, configuration is explicit, and no future-layer behavior has leaked into the foundation.
- The configuration, telemetry, and verification entry-point contracts in the Dependencies and Contracts sections are explicit and reproducible.
- V1 checks and the evidence listed above pass.
- Later-layer invariant ownership is preserved without implementation leakage.
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
