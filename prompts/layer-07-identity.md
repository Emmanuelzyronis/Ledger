# LEDGER — Layer 07: Identity

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement source identity, raw identity, canonical identity, and deterministic fingerprints without treating source IDs as universal transaction IDs.

## Scope

Implement only the responsibilities belonging to **Identity**.

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

Layer 6 canonical transactions. Use the exact identity algorithms, serialization, namespaces, and collision rules in `Architecture.md` §10.

## Allowed Changes

Implement source, raw, canonical, idempotency, correction, and audit-event identity functions/constraints. Do not create cross-source transaction IDs or reconcile records.

## Contracts

Use UTF-8 sorted-key canonical JSON, SHA-256 lowercase hex, namespaced IDs, and timestamp-free logical event keys exactly as specified in §10.

## Invariants Owned/Enforced

L-INV-003, L-INV-004, and L-INV-012.

## Verification

V2/V4 tests must cover replay stability, namespace isolation, identical payloads across batches, changed payload corrections, collision handling, and audit-event idempotency keys.

## Evidence

Record serialization fixtures, hashes, identity components, uniqueness outcomes, and cross-source isolation tests.

## Exit Condition

Exit only when representation identity is deterministic and demonstrably distinct from reconciliation identity.

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

- Identity is stable, explicit, collision-conscious, and independently verified.
- Identity, serialization, namespace, and collision contracts from the Contracts section are explicit.
- Identity-vector and replay tests pass.
- L-INV-003, L-INV-004, and L-INV-012 are evidenced.
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
