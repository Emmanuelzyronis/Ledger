# LEDGER — Layer 06: Normalization

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement deterministic source-to-canonical transaction transformation with versioned normalization semantics.

## Scope

Implement only the responsibilities belonging to **Normalization**.

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

Layers 4-5. Use the exact source mappings and canonical field contract in `Architecture.md` §§21-21.1.

## Allowed Changes

Implement deterministic source-to-canonical transformations and normalization-version registration. Do not perform candidate generation, matching, or reconciliation.

## Contracts

Map Source A and B names to the canonical names exactly; use UTC timestamps, fixed-point Decimal(20,4), Unicode NFC strings, and immutable canonical versions with supersession (§§10, 21, 27).

## Invariants Owned/Enforced

L-INV-002 and the canonical-version portion of L-INV-010.

## Verification

V2 tests must prove identical raw input plus version yields byte-identical canonical output, corrections yield new versions, and invalid records produce no canonical output.

## Evidence

Record source schema version, normalization version, canonical fingerprint, field mapping, and deterministic replay output.

## Exit Condition

Exit only when all canonical fields and mappings are fixed and normalization contains no reconciliation behavior.

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

- Identical raw input under the same normalization version produces identical canonical output.
- Source-to-canonical mapping and version contracts from the Contracts section are explicit.
- Deterministic replay tests pass.
- L-INV-002 and L-INV-010 are evidenced.
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
