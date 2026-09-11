# LEDGER — Layer 04: Raw Ingestion

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Implement source registration, batch creation, raw record ingestion, deterministic fingerprinting, and idempotency while preserving immutable evidence.

## Scope

Implement only the responsibilities belonging to **Raw Ingestion**.

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

Layers 1-3. Use only `source_a.v1` and `source_b.v1` from `Architecture.md` §21.1 and identity/idempotency rules in §10.

## Allowed Changes

Implement source registration, batch creation, raw-envelope persistence, schema-version capture, submission idempotency, and ingestion telemetry. Do not validate canonical business meaning or match records.

## Contracts

Apply the acceptance boundary and invalid-envelope rules in §22; use the raw identity and idempotency algorithms in §10; preserve original payload bytes/values and batch associations.

## Invariants Owned/Enforced

L-INV-001, L-INV-004, L-INV-005, and L-INV-012.

## Verification

V2/V3/V4 tests must cover both source schemas, malformed envelopes, repeated submissions, identical payloads in separate batches, changed-payload corrections, and no silent loss.

## Evidence

Record raw IDs, fingerprints, batch associations, duplicate-submission results, invalid envelopes, counters, and correlation IDs.

## Exit Condition

Exit only when retries reuse logical state, corrections create new versions, and every accepted or rejected input has explicit evidence.

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

- Repeated input does not create duplicate authoritative records and no accepted record silently disappears.
- Source schema, acceptance, identity, and idempotency contracts from the Contracts section are explicit.
- V2/V3/V4 ingestion tests pass.
- L-INV-001, L-INV-004, L-INV-005, and L-INV-012 are evidenced.
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
