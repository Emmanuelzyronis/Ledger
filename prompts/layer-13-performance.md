# LEDGER — Layer 13: Performance

## Mission

Implement **only this layer**.

Read and obey:

- `AGENTS.md`
- `Architecture.md`
- `prompts/README.md`

## Objective

Establish representative datasets, benchmark the pipeline, identify bottlenecks, and optimize only where evidence supports the change.

## Scope

Implement only the responsibilities belonging to **Performance**.

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

Layers 1-12. Use the benchmark evidence contract in `Architecture.md` §34; numerical SLOs remain deferred under D-009.

## Allowed Changes

Add representative fixtures, benchmark harnesses, measurements, and evidence-backed optimizations that preserve semantics. Do not introduce distributed infrastructure or alter matching rules.

## Contracts

Capture dataset manifest/checksum, machine/runtime/database profile, at least one warm-up and five measured iterations, median/p95 latency, throughput, memory, candidate distributions, and correctness comparison with the deterministic baseline.

## Invariants Owned/Enforced

No new business invariant; performance changes must regression-check all L-INV identifiers relevant to touched stages.

## Verification

Run reproducible benchmark and V1-V3 correctness checks before and after optimization. Report method and environment, not unsupported SLO claims.

## Evidence

Store benchmark manifest, raw measurements, comparison results, and optimization rationale.

## Exit Condition

Exit only when measured changes preserve deterministic outputs and the evidence is reproducible on the recorded environment.

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

- Performance is measured reproducibly without weakening correctness or explainability.
- Benchmark harness, environment, repeatability, and correctness-comparison contracts are explicit.
- Benchmark and regression checks pass with recorded evidence.
- All touched invariants remain evidenced.
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
