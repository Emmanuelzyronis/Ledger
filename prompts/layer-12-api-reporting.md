# LEDGER — Layer 12: API + Reporting

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Expose business operations through an API and derived reporting/query views without allowing callers to bypass domain rules.

## Scope

Implement only the responsibilities belonging to **API + Reporting**.

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

Layers 1-11. Use the local JSON/CLI ingestion and HTTP reporting/authorized-resolution interface decision D-010, security ownership §35, and projection contract §38.

## Allowed Changes

Expose business operations through authorized interfaces, read authoritative state, build rebuildable projections/exports, and expose health/metrics views. Do not write authority directly from handlers or dashboards.

## Contracts

API operations must call domain/application services; source, batch, reconciliation, discrepancy, resolution, and audit access is authorization-scoped. Projections/exports are read-only, eventually consistent, watermarkable, and rebuildable.

## Invariants Owned/Enforced

API/projection portions of L-INV-005, L-INV-006, L-INV-008, and L-INV-010.

## Verification

V3/V4 tests must cover authentication integration, authorization boundaries, forbidden direct mutation, projection rebuilds, stale reads, export redaction, and health/readiness semantics.

## Evidence

Record request/response contracts, authorization decisions, projection watermarks, rebuild output, redaction checks, and correlation IDs.

## Exit Condition

Exit only when interfaces cannot bypass domain rules and deleting a projection/export cannot delete authoritative state.

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

- Interfaces expose authoritative state safely and reports remain derived.
- API authorization, service-boundary, projection, export, and health contracts from the Contracts section are explicit.
- V3/V4 interface and rebuild tests pass.
- L-INV-005, L-INV-006, L-INV-008, and L-INV-010 are evidenced.
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
