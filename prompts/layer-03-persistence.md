# LEDGER — Layer 03: Persistence

## Mission

Implement **only this layer and its remaining contract reconciliation**. Existing Layer 3 code is evidence and must be preserved unless it violates the architecture.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement authoritative persistence and repositories for the domain state. Enforce immutability, uniqueness, relationships, and transactional boundaries required by the architecture.

For the current repository, these reconciliation-version, audit-sequence, and atomic state-plus-audit contracts are the completion criteria and are now the evidence to preserve when reviewing this layer.

## Scope

Implement only the responsibilities belonging to **Persistence**.

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

Layers 1-2. Use the canonical/source contracts in `Architecture.md` §§10, 21-24 and relational authority in §33.

## Allowed Changes

Implement repositories, relational mappings, uniqueness constraints, immutable/versioned writes, and transaction boundaries. Persistence ports are application-owned; concrete database code stays infrastructure-side.

## Contracts

Persist every authoritative entity, enforce raw/canonical/reconciliation/audit immutability and supersession, implement identity uniqueness from §10, and make state-plus-audit writes atomic as required by §§29-32.

## Invariants Owned/Enforced

L-INV-001, L-INV-004, L-INV-008, L-INV-010, and L-INV-011 through storage constraints and transactions.

## Verification

V2/V3 tests must cover uniqueness, immutable writes, correction versions, atomic rollback, idempotent retries, and append-only audit events.

## Evidence

Record schema/repository contract, constraint checks, transaction rollback results, and repeatability evidence.

## Exit Condition

Exit only when all authoritative state has one repository owner and no persistence operation can overwrite historical evidence.

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

- Authoritative records can be stored/retrieved correctly and critical invariants are enforced.
- Repository, uniqueness, immutability, versioning, and atomicity contracts from the Contracts section are explicit.
- V2/V3 persistence tests pass.
- L-INV-001, L-INV-004, L-INV-008, L-INV-010, and L-INV-011 are evidenced.
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
