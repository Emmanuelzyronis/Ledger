# LEDGER — Layer 08: Candidate Generation

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement indexed/bounded candidate generation. Keep search-space reduction separate from final matching and avoid naive all-pairs matching.

## Scope

Implement only the responsibilities belonging to **Candidate Generation**.

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

Layer 7 identities and canonical transactions. Use candidate indexes, completeness, ordering, and exclusions in `Architecture.md` §§11 and 25.

## Allowed Changes

Implement only indexed candidate retrieval and candidate evidence. Do not evaluate final correspondence or assign reconciliation outcomes.

## Contracts

Generate the union of exact normalized transaction-reference candidates and exact `(currency, amount, occurred_date)` candidates within inclusive ±2 UTC calendar days. Order by `canonical_id`; apply no hidden filters; retain the complete proposal set.

## Invariants Owned/Enforced

Candidate portions of L-INV-006, L-INV-007, and L-INV-009.

## Verification

V2/V3 tests must prove completeness for the defined legitimate-counterpart set, bounded retrieval, deterministic ordering, exclusion behavior, and no O(n²) all-pairs path.

## Evidence

Record index keys, candidate counts/distributions, ordered candidate IDs, excluded-record reasons, and benchmark inputs.

## Exit Condition

Exit only when candidate generation is deterministic, bounded, complete for its stated contract, and makes no matching decision.

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

- Candidate generation is deterministic, measurable, bounded, and has explicit completeness semantics.
- Index, completeness, exclusion, ordering, and boundedness contracts from the Contracts section are explicit.
- Candidate determinism/completeness tests pass.
- Candidate portions of L-INV-006, L-INV-007, and L-INV-009 are evidenced.
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
