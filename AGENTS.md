# LEDGER — AGENTS.md

## Repository frontier

Layers 1-15 are implemented and verified: Foundation, Domain Model, Persistence, Raw Ingestion, Validation, Normalization, Identity, Candidate Generation, Matching, Reconciliation, Resolution + Audit, API + Reporting, Performance, Failure Verification, and Product Proof. Do not restart completed layers.

Post-Layer-15 work is organized as the **LEDGER Production Readiness** program (Linear project `LEDGER Production Readiness`) and is executed one epic at a time under the same authority, invariant, verification, and stop-condition rules as the layers. Epics 1-4 are complete: baseline + late-arrival architecture correction (LA-1), service entrypoint and process model, authentication/authorization/request hardening, and the versioned OpenAPI contract. The next authorized epic is Epic 5 (database operations), followed by observability, deployment, staging, and rollout. Do not start an epic that is not authorized in that project, and do not skip ahead of the current epic.

## 1. Project Identity

LEDGER is a transaction reconciliation engine with a deliberately defined canonical transaction model, multiple source representations, deterministic matching, ambiguity handling, immutable evidence, and auditable resolutions.

The authoritative architecture is `Architecture.md`.

`Architecture.md` is the source of truth for business semantics, schemas, state machines, deterministic algorithms, security ownership, observability ownership, and evidence contracts. Layer prompts may narrow implementation scope but may not override it. If a prompt conflicts with the architecture, stop and report the conflict.

## 2. Engineering Mission

Build LEDGER so independently produced transaction records can be ingested, preserved, validated, normalized, identified, candidate-generated, deterministically matched, reconciled, resolved, audited, reported, and verified.

The first implementation is explicitly **1:1 reconciliation**.

Do not expand into 1:N, N:M, settlement allocation, ML matching, distributed processing, or enterprise infrastructure unless the architecture is explicitly revised.

## 3. Authority

Priority order:

1. `Architecture.md`
2. invariant/contract documents
3. current layer prompt
4. existing implementation
5. agent assumptions

If implementation conflicts with architecture, stop and report the conflict. Do not silently redesign the architecture through code.

## 4. Source of Truth

- Raw evidence → raw-record store
- Batch state → batch metadata
- Canonical transaction → canonical transaction store
- Reconciliation decision → reconciliation record
- Discrepancy → discrepancy record
- Resolution → resolution record
- Audit history → append-only audit records
- Reports/UI → derived projections
- Metrics/logs → observability only

Queues, caches, dashboards, logs, exports, and temporary process state are never authoritative business state.

## 5. Non-Negotiable Invariants

- Accepted raw input is immutable.
- Normalization is deterministic.
- Identity generation is deterministic.
- Repeated ingestion is idempotent.
- No accepted input disappears without an explicit state.
- Every reconciliation decision is explainable.
- Ambiguous candidates are never silently forced into a match.
- Audit history is preserved.
- 1:1 reconciliation constraints are enforced.
- Corrections preserve historical evidence.
- Illegal state transitions are rejected.
- Source-native IDs are not universal transaction IDs.

Do not weaken an invariant to make a test pass.

Candidate generation only reduces the search space; matching alone evaluates correspondence. Ambiguity is never silently resolved. Historical raw records, canonical versions, reconciliation versions, discrepancies, resolutions, and audit events are never destructively overwritten. Reports, projections, and exports are read-only derived state and are never authoritative.

## 6. Failure Is First-Class

Every major operation must consider success, validation failure, duplicate input, retry, timeout, restart, partial completion, dependency failure, late arrival, and correction.

A happy-path implementation is not complete.

## 7. Determinism

Same inputs + same versions + same configuration must produce the same result.

If ordering can affect an outcome, define the ordering rule explicitly.

## 8. Domain / Infrastructure Separation

Domain owns transaction semantics, matching, reconciliation outcomes, state transitions, invariants, discrepancies, and resolutions.

Infrastructure owns database access, HTTP, CLI, storage, logging, metrics, connectors, and deployment.

Security and observability are cross-cutting obligations. Foundation establishes secure configuration and telemetry boundaries; ingestion/validation protect untrusted input; API/reporting enforces authentication, authorization, access scoping, and export controls; every processing layer emits its assigned telemetry; failure verification tests the controls.

## 9. Modular Architecture

Use logical modules for:

- ingestion
- validation
- normalization
- identity
- candidate generation
- matching
- reconciliation
- resolution
- audit
- reporting
- observability

These are responsibilities, not automatic network boundaries.

## 10. Layered Execution Rule

Implement **one layer at a time**.

Before a layer:

1. Read `AGENTS.md`.
2. Read `Architecture.md`.
3. Read the layer prompt.
4. Inspect the repository.
5. Identify the current layer state.

During the layer:

- implement only assigned scope,
- add required tests,
- preserve existing contracts,
- stop on architectural ambiguity.

After the layer:

- run verification,
- inspect the diff,
- verify architecture,
- report evidence,
- stop.

Never automatically continue to the next layer.

Architectural processing stages and implementation layers are different concepts. Processing stages describe data semantics; the 15 implementation layers describe repository build order. Use the terminology and mapping in `Architecture.md` §6 and §52.

## 11. Forbidden Behavior

Do not:

- redesign unrelated modules,
- introduce unrelated dependencies,
- bypass invariants,
- mutate raw historical evidence,
- introduce premature distributed infrastructure,
- add speculative abstractions,
- rewrite working code for style alone,
- silently change public contracts.

## 12. Verification

Every layer requires both:

### Implementation verification
Does the code work?

### Architectural verification
Does the code implement the intended architecture?

Passing tests alone is insufficient.

Every invariant must have an identified owner, enforcement mechanism, verification level, and evidence artifact. Completion claims require reproducible evidence, not only a green test command.

## 13. Testing

Use relevant:

- unit tests
- integration tests
- idempotency tests
- deterministic/property tests
- state-transition tests
- failure/recovery tests
- performance tests
- product-proof tests

## 14. Security

LEDGER may process sensitive financial information.

- Never hardcode credentials.
- Validate untrusted input.
- Avoid unnecessary sensitive data in logs.
- Preserve authorization boundaries.
- Protect raw records and exports.
- Use secure configuration defaults.

## 15. Performance

Measure before optimizing.

Do not use naive O(n²) all-pairs matching as the normal strategy.

Performance claims must state dataset size, environment, method, and result.

Layer 13 benchmark evidence is produced by `benchmarks/run_performance.py` and stored in
`evidence/performance-baseline.json`; numerical SLOs remain deferred by Architecture D-009.

Layer 14 failure-verification evidence is produced by `tests/test_failure_verification.py`
and documented in `docs/failure-verification.md`.

Layer 15 product-proof evidence is produced by
`PYTHONPATH=src python3 product_proof/run_product_proof.py`, covered by
`tests/test_product_proof.py`, and documented in `docs/product-proof.md`.

## 16. Architecture Changes

If implementation requires changing `Architecture.md`, stop and report:

- contradiction,
- proposed change,
- reason,
- consequences.

Do not silently update architecture to fit code.

## 17. Agent Report

Every layer must report:

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

Claims such as “complete” or “verified” require evidence.

## 18. Stop Conditions

Stop and ask for review if:

- a required state is undefined,
- source-of-truth ownership is unclear,
- a transition is ambiguous,
- a new domain concept is required,
- an invariant cannot be satisfied,
- a security boundary is unclear,
- correctness depends on undocumented behavior,
- the layer requires changing an earlier contract.

Do not invent unresolved business semantics during implementation. Use only the resolved contracts in `Architecture.md`; escalate an actual contradiction rather than selecting a new rule locally.

## 19. Final Principle

> Don't accept completion because something looks complete. Verify it.

LEDGER is successful when its behavior can be demonstrated, explained, reproduced, and defended with evidence.
