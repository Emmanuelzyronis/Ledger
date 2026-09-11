# LEDGER Layer Execution Prompts

Run these prompts sequentially with the engineering agent.

Current repository status: Layers 1-12 are completed and verified; Layer 13 is the next authorized layer; Layers 13-15 are future and not implemented.

The architecture defines ten **processing stages** (the logical movement and meaning of data) and fifteen **implementation layers** (the controlled repository build order). The numbered files below are implementation layers and map to the processing stages as specified in `Architecture.md` §6 and §52. An implementation layer may establish support for a stage without implementing later business behavior.

1. `layer-01-foundation.md`
2. `layer-02-domain-model.md`
3. `layer-03-persistence.md`
4. `layer-04-raw-ingestion.md`
5. `layer-05-validation.md`
6. `layer-06-normalization.md`
7. `layer-07-identity.md`
8. `layer-08-candidate-generation.md`
9. `layer-09-matching.md`
10. `layer-10-reconciliation.md`
11. `layer-11-resolution-audit.md`
12. `layer-12-api-reporting.md`
13. `layer-13-performance.md`
14. `layer-14-failure-verification.md`
15. `layer-15-product-proof.md`

## Execution rule

Run exactly one layer at a time.

Before each layer, read:

- `AGENTS.md`
- `Architecture.md`
- the selected layer prompt

After each layer:

- verify behavior,
- inspect the diff,
- verify architecture,
- record evidence,
- stop.

If a layer exposes an architectural contradiction, stop implementation and report it.

Before implementation, the selected prompt's dependency and contract sections must be satisfied by prior layers or by explicit architecture sections. A prompt never authorizes inventing a missing schema, state transition, matching rule, security boundary, or observability contract. Escalate such a gap and do not continue automatically.

Cross-cutting prerequisites:

- `Architecture.md` is authoritative; prompts cannot override it.
- The modular-monolith and relational-authority decisions apply to every layer.
- Security and observability obligations apply in every layer according to their assigned owners.
- Raw evidence and versioned decisions are immutable; projections and exports are derived/read-only.
- Verification must identify tests and evidence for the layer's owned invariants.
