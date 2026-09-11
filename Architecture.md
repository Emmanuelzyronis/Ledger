# LEDGER Architecture v1.0

**Project:** LEDGER  
**Document:** Architecture Specification  
**Version:** 1.0  
**Status:** Architecture baseline ready for controlled implementation  
**Primary concern:** Correct, deterministic, explainable transaction reconciliation

---

## 1. Architectural Identity

> **LEDGER is a transaction reconciliation engine with a deliberately defined canonical transaction model, multiple source representations, deterministic matching, ambiguity handling, immutable evidence, and auditable resolutions.**

LEDGER is designed to determine whether independently produced transaction records represent the same underlying transaction, identify discrepancies without silently forcing incorrect matches, preserve the evidence behind every decision, and provide an auditable history of how discrepancies were resolved.

The system is deliberately bounded around **1:1 transaction reconciliation** for the first implementation.

One transaction from Source A may correspond to at most one transaction from Source B.

Many-to-one settlement, one-to-many splits, partial payments, and complex settlement allocation are explicitly outside the v1.0 core.

---

# 2. Mission

LEDGER exists to transform imperfect records from independent systems into a deterministic, explainable reconciliation result.

### Mission statement

> **Build a reconciliation engine that can ingest independently produced transaction records, normalize them into a canonical model, deterministically identify corresponding records, classify discrepancies, preserve immutable evidence, and explain every reconciliation decision.**

The system must optimize for:

- correctness
- determinism
- traceability
- idempotency
- explainability
- controlled performance
- operational visibility

Performance matters, but **performance must never be achieved by weakening correctness guarantees.**

---

# 3. Product Scope

## 3.1 In scope

LEDGER v1.0 supports:

- multiple transaction sources
- batch ingestion
- raw record preservation
- schema validation
- deterministic normalization
- source-level identity
- canonical transaction representation
- deterministic candidate generation
- deterministic 1:1 matching
- ambiguity detection
- duplicate detection
- reconciliation classification
- discrepancy creation
- auditable resolution
- immutable audit evidence
- replay/reprocessing
- idempotent ingestion
- late-arriving records
- corrected source records through versioned ingestion
- reconciliation reporting
- operational metrics

## 3.2 Explicitly out of scope

LEDGER v1.0 does not attempt to be:

- a general accounting ledger
- a payment processor
- a banking core
- a distributed database
- a generic ETL platform
- an ML-powered fuzzy matching system
- a workflow engine
- a multi-region distributed system
- a general-purpose financial settlement engine
- a 1:N or N:M reconciliation engine
- an automatic human-decision replacement

---

# 4. Architectural Principles

## 4.1 Every important state has one authority

Each state must have a clearly defined source of truth.

| State | Authority |
|---|---|
| Raw input | Raw record store |
| Batch state | Batch metadata |
| Canonical transaction | Canonical transaction store |
| Reconciliation decision | Reconciliation record |
| Discrepancy | Discrepancy record |
| Resolution | Resolution record |
| Audit history | Audit event store |
| Metrics | Observability system |
| Reports | Derived projections |

Queues, caches, dashboards, logs, and exported reports are never authoritative for business state.

---

## 4.2 Derived representations remain derived

A normalized transaction is derived from raw input.

A candidate is derived from canonical transactions.

A report is derived from reconciliation state.

If a projection disappears, the authoritative state must remain recoverable.

---

## 4.3 Raw evidence is immutable

Once accepted into the system, the original source representation cannot be modified.

Corrections create a new record/version and preserve the relationship to the original.

---

## 4.4 Determinism is a product requirement

Given:

- the same source records
- the same normalization rules
- the same identity rules
- the same matching rules
- the same configuration

LEDGER must produce the same result.

---

## 4.5 Ambiguity is a valid outcome

The system must never convert uncertainty into a false positive merely to increase match rate.

If multiple candidates satisfy the highest applicable rule in `standard_v1`, the result is:

`AMBIGUOUS`

unless a future architecture revision explicitly adds a deterministic rule; v1.0 has no such tie-breaker.

---

## 4.6 Failure is part of the architecture

Every major operation must define behavior for:

- success
- validation failure
- duplicate input
- timeout
- retry
- process restart
- partial completion
- dependency failure
- late arrival
- correction

---

# 5. High-Level Architecture

```text
                     ┌──────────────────────┐
                     │   Source Systems     │
                     │ Bank / PSP / Ledger  │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │    INGESTION         │
                     │ batch + idempotency  │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │    RAW RECORDS       │
                     │ immutable evidence   │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │    VALIDATION        │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │   NORMALIZATION      │
                     │ source → canonical   │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │      IDENTITY        │
                     │ deterministic IDs    │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │ CANDIDATE GENERATION │
                     │ indexed search space │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │      MATCHING        │
                     │ deterministic rules  │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │   RECONCILIATION     │
                     │ classify outcome     │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────┐
                     │   RESOLUTION     │
                     │ authorized only  │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │      AUDIT       │
                     │ immutable trail  │
                     └────────┬─────────┘
                              ▼
                    ┌──────────────────────┐
                    │     PROJECTIONS      │
                    │ API / reports / UI   │
                    └──────────────────────┘
```

---

# 6. Architectural Stages and Implementation Layers

LEDGER has two related but distinct structures:

1. **Architectural processing stages** describe the logical data semantics and pipeline.
2. **Implementation layers** describe the controlled repository build order.

The processing stages are the ten-stage pipeline shown below. They must not be confused with the fifteen implementation layers in Section 52.

| Architectural stage | Implementation layers |
|---|---|
| Ingestion | 1 Foundation, 3 Persistence, 4 Raw Ingestion |
| Validation | 5 |
| Normalization | 6 |
| Identity | 7 |
| Candidate Generation | 8 |
| Matching | 9 |
| Reconciliation | 10 |
| Resolution and Audit | 11 |
| Projection/Reporting and Observability interfaces | 12 |
| Performance, failure verification, and product proof | 13-15 |

```text
┌───────────────────────────────────────────────┐
│  LAYER 10 — PROJECTION / REPORTING            │
├───────────────────────────────────────────────┤
│  LAYER 9  — AUDIT                             │
├───────────────────────────────────────────────┤
│  LAYER 8  — RESOLUTION                        │
├───────────────────────────────────────────────┤
│  LAYER 7  — RECONCILIATION                    │
├───────────────────────────────────────────────┤
│  LAYER 6  — MATCHING                          │
├───────────────────────────────────────────────┤
│  LAYER 5  — CANDIDATE GENERATION              │
├───────────────────────────────────────────────┤
│  LAYER 4  — IDENTITY                          │
├───────────────────────────────────────────────┤
│  LAYER 3  — NORMALIZATION                     │
├───────────────────────────────────────────────┤
│  LAYER 2  — VALIDATION                         │
├───────────────────────────────────────────────┤
│  LAYER 1  — RAW INGESTION                     │
└───────────────────────────────────────────────┘
```

The layers describe **responsibility and data semantics**, not necessarily separate deployable services.

The initial implementation should prefer a modular pipeline over premature microservices.

---

# 7. Layer 1 — Raw Ingestion

## Responsibility

Accept source records and preserve their original representation.

Inputs may arrive through:

- API
- CLI
- file import
- batch upload
- future connector

## Guarantees

Every accepted raw record receives:

- immutable record identity
- source identity
- batch identity
- ingestion timestamp
- source-native identifier where available
- content fingerprint
- original payload

## Idempotency

A source record must not be ingested twice merely because the same batch is retried.

A uniqueness strategy must exist around source identity and/or deterministic content identity.

```text
Input
  │
  ▼
Calculate fingerprint
  │
  ├── already known ──► existing record
  │
  └── new ────────────► immutable RawRecord
```

---

# 8. Layer 2 — Validation

Validation determines whether an input is structurally and semantically acceptable for processing.

Validation categories:

### Structural

- required fields exist
- field types are valid
- schema is recognized

### Semantic

- amount is valid
- currency is recognized
- timestamp is parseable
- source-specific constraints hold

### Business constraints

- transaction direction is valid
- required identifiers are present
- unsupported states are rejected

Invalid records are **not silently discarded**.

They become explicitly classified invalid records with evidence.

---

# 9. Layer 3 — Normalization

Normalization converts source-specific representations into the canonical transaction model.

Example:

```text
Bank A
--------------------------------
txn_id      = "A-18372"
posted      = "2026/09/01"
amount      = "1,250.00"
currency    = "USD"
description = "ACME LTD / INV 44"

                │
                ▼

Canonical Transaction
--------------------------------
source_record_id = A-18372
occurred_at      = 2026-09-01T00:00:00
amount           = 1250.00
currency         = USD
reference        = ACME LTD / INV 44
```

Normalization must be deterministic.

It must not perform reconciliation.

Normalization answers:

> **What does this source record mean in the canonical domain?**

It does not answer:

> **Which other record does it match?**

---

# 10. Layer 4 — Identity

LEDGER distinguishes several identities.

## 10.1 Source identity

Identifies the record inside its originating source.

Conceptually:

```text
(source_id, source_record_id)
```

The serialized source identity is `src:<source_id>:<source_record_id>`. It is namespaced and never compared across sources as a transaction identity.

## 10.2 Raw identity

Identifies the immutable ingested representation. Raw identity is:

`raw:<source_id>:<schema_version>:<sha256(canonical_payload)>`

The canonical payload is UTF-8 JSON with sorted keys, no insignificant whitespace, Unicode NFC strings, normalized line endings, and exact source values. Hashes are SHA-256 lowercase hexadecimal. A repeated identical payload in another batch reuses the existing raw record and adds the batch association; it does not create a second raw record. A changed payload for the same source record is a correction and receives a new raw identity linked to the prior raw record.

## 10.3 Canonical identity

Identifies the normalized representation/version:

`can:<raw_record_id>:<normalization_version>:<canonical_version>`

The canonical fingerprint is SHA-256 over the canonical serialization of semantic fields (`occurred_at`, `amount`, `currency`, `direction`, `transaction_type`, `account_reference`, `transaction_reference`, `description`, and `transaction_status`) and excludes generated/provenance fields and timestamps. Uniqueness is enforced on `(raw_record_id, normalization_version, canonical_version)`.

## 10.4 Cross-source transaction identity

This is intentionally **not assumed to exist before matching**.

A source record's ID must not be treated as a universal transaction ID.

This distinction is fundamental.

```text
Source A ID ──┐
              ├──► Candidate / Match ──► Reconciliation Identity
Source B ID ──┘
```

Cross-source identity is represented only by a reconciliation pair. It is never generated from matching fields before reconciliation.

## 10.5 Idempotency and correction identity

An explicit client idempotency key, when supplied, is namespaced by operation and source. When absent, the raw identity is the idempotency key for ingestion. Idempotency keys are unique for the operation scope and return the original logical result on retry.

Correction identity is the tuple `(source_id, source_record_id, raw_record_id)`. Corrections create a new raw record, canonical version, reconciliation version, and audit events linked by supersession; prior records remain immutable.

Audit event identity is:

`audit:<sha256(event_type, entity_type, entity_id, attempt_id, stage_version, sequence)>`

The logical key excludes timestamps and actor display names. The append-only store rejects duplicate event identities and retries return the existing event.

---

# 11. Layer 5 — Candidate Generation

Candidate generation reduces the search space before actual matching.

It answers:

> **Which records could plausibly correspond?**

It does not make the final reconciliation decision.

Naive matching would resemble:

```text
A1 ↔ B1
A1 ↔ B2
A1 ↔ B3
...
A2 ↔ B1
A2 ↔ B2
...
```

This approaches O(n²).

Instead, candidate generation uses deterministic indexed keys and bounded windows.

Potential candidate dimensions include:

- amount
- currency
- transaction date
- account/reference (evidence only; not an exclusion key)
- source reference
- normalized description/reference
- fixed inclusive plus or minus 2 UTC calendar-day window

Example:

```text
Source A transaction
      │
      ├── amount = 1250.00
      ├── currency = USD
      └── date ± 2 days
               │
               ▼
       Candidate Index
               │
        ┌──────┼──────┐
        ▼      ▼      ▼
       B17    B42    B91
```

Candidate generation uses the union of two deterministic indexes:

1. `transaction_reference` exact match when both records have a non-empty normalized reference.
2. `(currency, amount, occurred_date)` with an inclusive date window of **plus or minus 2 UTC calendar days**.

Currency must be equal and amount must be exactly equal as fixed-point decimals. Account and description are retained as evidence but are not exclusion keys. Candidates outside both keys are excluded. Candidate output is ordered by `canonical_id` ascending.

A legitimate counterpart for v1.0 is a valid canonical transaction from the opposite source that satisfies either index definition. The union is complete for that definition; candidate generation may not silently apply additional filters.

---

# 12. Layer 6 — Matching

Matching evaluates candidates using deterministic rules.

Matching is responsible for deciding whether a candidate pair represents the same transaction.

A v1.0 uses this exact rule hierarchy:

```text
M-001 exact transaction reference
        │
        ▼
M-002 exact amount + currency + date window
        │
        ▼
No unique candidate
```

Rules are immutable configuration in `standard_v1`:

| Rule | Priority | Required fields | Comparison | Unique result | Multiple results | No result |
|---|---:|---|---|---|---|---|
| M-001 | 100 | non-empty `transaction_reference` on both sides | exact normalized string equality | continue with the pair as the selected proposal | `AMBIGUOUS` | evaluate M-002 |
| M-002 | 50 | `amount`, `currency`, `occurred_at` | exact amount/currency and date difference <= 2 UTC calendar days | selected proposal | `AMBIGUOUS` | `UNMATCHED_A` or `UNMATCHED_B` |

If M-001 produces a unique pair but amount, currency, or direction differs, the pair is retained and Reconciliation classifies it as `MISMATCHED`. If a higher-priority rule is ambiguous, lower-priority rules cannot override it. Conflicting unique proposals are handled by the global 1:1 algorithm below.

Every decision should retain:

- rule identifier
- rule version
- input identifiers
- relevant field values
- decision
- decision timestamp
- candidate ordering and all rejected candidates

---

# 13. Ambiguity Model

Suppose:

```text
A17
amount = 100.00
currency = USD
date = Sep 3
```

and:

```text
B41 → 100.00 USD → Sep 3
B57 → 100.00 USD → Sep 3
```

If no deterministic rule distinguishes them:

```text
A17 → AMBIGUOUS
```

not:

```text
A17 → B41
```

The system preserves the candidate set as evidence.

This makes ambiguity measurable rather than invisible.

---

# 14. Duplicate Detection

Duplicates are distinct from unmatched records.

Example:

```text
Source B:

B100 → $250
B101 → $250
B102 → $250

All three may represent the same underlying source event.
```

Duplicate detection identifies source-side or reconciliation-level duplication according to the explicit rules below.

A duplicate must not accidentally become a successful 1:1 match.

## 14.1 Duplicate taxonomy

**Submission duplicate** means the same ingestion operation is received again with the same operation-scoped idempotency key, or the same `(source_id, source_record_id, raw_identity)`. The existing raw record, batch association, and logical result are reused. Submission duplicates do not create a `DUPLICATE` reconciliation outcome and emit one `SUBMISSION_DUPLICATE` audit event at most.

**Business duplicate** means either identical canonical fingerprints under distinct source-native IDs within one source, or a one-to-many/many-to-one proposal conflict. Business duplicates are authoritative reconciliation outcomes, preserve all involved records, and emit `DUPLICATE_DETECTED` audit events.

Business duplicates are detected in two deterministic cases: (a) distinct source records in the same source have identical canonical fingerprints, or (b) the proposal graph contains a one-to-many or many-to-one conflict. All records in the conflict component are classified `DUPLICATE`; no automatic winner is selected.

---

# 15. Layer 7 — Reconciliation

The reconciliation layer converts matching observations into a business outcome.

Primary v1.0 outcomes:

```text
MATCHED
MISMATCHED
UNMATCHED_A
UNMATCHED_B
AMBIGUOUS
DUPLICATE
INVALID
```

## Meaning

### MATCHED

Exactly one valid counterpart satisfies the matching policy.

### MISMATCHED

A unique M-001 counterpart was identified, but exact amount, currency, or direction comparison fails.

### UNMATCHED_A

A Source A transaction has no eligible Source B counterpart.

### UNMATCHED_B

A Source B transaction has no eligible Source A counterpart.

### AMBIGUOUS

Multiple plausible counterparts remain.

### DUPLICATE

The record participates in a detected duplication condition.

### INVALID

The record could not legitimately enter reconciliation because validation failed.

`MISMATCHED` requires a unique proposed counterpart and at least one failed reconciliation comparison. `UNMATCHED_A` and `UNMATCHED_B` are used only when no candidate/proposal exists on the corresponding side. `AMBIGUOUS` is used when one record has multiple candidates satisfying the highest applicable rule. `DUPLICATE` is used for the duplicate conditions defined in §14 and for global 1:1 conflicts.

---

# 16. Reconciliation State

A reconciliation record is the authoritative representation of the decision.

Conceptually:

```text
Reconciliation
-------------------------
id
batch_id
source_a_record_id
source_b_record_id
outcome
rule_version
evidence
reconciliation_version
supersedes_reconciliation_id
created_at
current_state (derived from latest non-superseded version)
```

A reconciliation must not rely on the report layer to determine whether two records matched.

Reconciliation versions are immutable. There is no in-place `updated_at`; a new decision is a new version. `current_state` is a read-time derivation from the latest non-superseded version and is never independently authoritative.

---

# 17. Layer 8 — Resolution

Resolution handles discrepancies requiring an explicit decision.

A resolution may be:

- automatic
- manually approved
- rejected
- deferred

The resolution must preserve:

- previous outcome
- resolution type
- actor
- reason
- evidence
- timestamp
- rule/version where applicable

The system should not mutate history to make the final state look clean.

Instead:

```text
Original decision
       │
       ▼
Discrepancy
       │
       ▼
Resolution
       │
       ▼
Current derived status
```

---

# 18. Layer 9 — Audit

Audit is an immutable record of significant state transitions and decisions.

Example:

```text
AuditEvent
--------------------------------
event_id
entity_type
entity_id
event_type
actor
timestamp
previous_state
new_state
reason
metadata
batch_id
attempt_id
record_id
reconciliation_id
causation_event_id
sequence
stage_version
```

Examples:

```text
RECORD_INGESTED
RECORD_VALIDATED
NORMALIZATION_COMPLETED
MATCH_EVALUATED
RECONCILIATION_CREATED
DISCREPANCY_CREATED
RESOLUTION_APPLIED
BATCH_COMPLETED
```

Audit history is append-only.

`event_id` is the deterministic identity defined in §10.5. `timestamp` is the UTC commit time and is not used for ordering; `sequence` is a strictly increasing per-entity sequence allocated transactionally. Required event types are `BATCH_RECEIVED`, `BATCH_STATE_CHANGED`, `SUBMISSION_DUPLICATE`, `RECORD_INGESTED`, `RECORD_INVALID`, `NORMALIZATION_COMPLETED`, `MATCH_EVALUATED`, `DUPLICATE_DETECTED`, `RECONCILIATION_CREATED`, `DISCREPANCY_CREATED`, `RESOLUTION_APPLIED`, and `PROJECTION_REBUILT`.

Ordering is defined only within one entity by `sequence`; cross-entity timestamp ordering has no business meaning.

Every authoritative state transition and every processing attempt transition emits exactly one corresponding logical event. The event write and the authoritative state write occur in one relational transaction. A retry with the same logical event identity returns the existing event; a failed transaction writes neither state nor event.

---

# 19. Layer 10 — Projection / Reporting

Reporting is derived from authoritative state.

Potential views:

- reconciliation summary
- matched transactions
- mismatches
- unmatched records
- ambiguous records
- duplicates
- invalid records
- resolution history
- batch health
- processing latency
- throughput
- error rates

```text
Authoritative State
       │
       ├────► API
       ├────► Dashboard
       ├────► Reports
       └────► Exports
```

A deleted report must never imply deleted reconciliation state.

---

# 20. Core Domain Model

```text
                         ┌──────────────┐
                         │    Source    │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │    Batch     │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  RawRecord   │
                         └──────┬───────┘
                                │
                                ▼
                     ┌────────────────────┐
                     │ CanonicalTransaction│
                     └─────────┬──────────┘
                               │
                     ┌─────────▼─────────┐
                     │ MatchCandidate(s) │
                     └─────────┬─────────┘
                               │
                               ▼
                     ┌───────────────────┐
                     │  Reconciliation   │
                     └───────┬───────────┘
                             │
                 ┌───────────┼───────────┐
                 ▼           ▼           ▼
          Discrepancy   Resolution    AuditEvent
```

---

# 21. Canonical Transaction Model

The canonical transaction model is the domain center of LEDGER.

The v1.0 canonical contract is:

```text
CanonicalTransaction
--------------------------------
canonical_id                 string, required, immutable
source_id                    string, required, immutable
raw_record_id                string, required, immutable
source_record_id             string, required, immutable
occurred_at                  UTC timestamp, required, immutable per version
amount                       fixed-point Decimal(20,4), required
currency                     uppercase ISO-4217 code, required
direction                    CREDIT or DEBIT, required
transaction_type             string, optional
account_reference            string, optional
transaction_reference        string, optional
description                  string, optional
transaction_status           string, optional source-native status
normalization_version        string, required
canonical_version            positive integer, required
supersedes_canonical_id      string, optional
canonical_fingerprint        SHA-256 hex string, required
created_at                   UTC timestamp, required
```

Amounts are represented as fixed-point decimal values in the stated currency units; binary floating point is forbidden. Timestamps are normalized to UTC. Strings are Unicode text normalized with Unicode NFC and trimmed according to the source adapter contract.

The canonical record is immutable. A correction creates a new canonical version with `supersedes_canonical_id`; no canonical row is updated in place.

Candidate generation may use `amount`, `currency`, the calendar date of `occurred_at`, `account_reference`, `transaction_reference`, and normalized `description`. Matching may use only the fields and comparisons defined in Section 25. `transaction_status` is informational and is not a matching key.

The important architectural property is:

> Source-specific representations map into one deliberately defined domain representation.

## 21.1 Initial source schemas

v1.0 defines exactly two source representations. Each record is a JSON object with a schema version.

**Source A (`source_a.v1`)**

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `record_id` | string | yes | Source-native identifier |
| `occurred_at` | string | yes | ISO-8601 timestamp with offset, or `YYYY-MM-DD` interpreted as UTC midnight |
| `amount` | string | yes | Decimal value with `.` separator and optional sign, maximum 4 fractional digits |
| `currency` | string | yes | Three-letter ISO-4217 code |
| `direction` | string | yes | `CREDIT` or `DEBIT` |
| `account_reference` | string | no | Source account or counterparty reference |
| `transaction_reference` | string | no | Source transaction/invoice reference |
| `description` | string | no | Free text |
| `transaction_type` | string | no | Source transaction type |

**Source B (`source_b.v1`)** has the same semantic fields and types, with these source-native names:

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | string | yes | Source-native identifier |
| `posted` | string | yes | ISO-8601 timestamp with offset, or `YYYY-MM-DD` interpreted as UTC midnight |
| `value` | string | yes | Decimal value with `.` separator and optional sign, maximum 4 fractional digits |
| `ccy` | string | yes | Three-letter ISO-4217 code |
| `side` | string | yes | `CREDIT` or `DEBIT` |
| `account_ref` | string | no | Source account or counterparty reference |
| `reference` | string | no | Source transaction/invoice reference |
| `memo` | string | no | Free text |
| `type` | string | no | Source transaction type |

The source schema version is carried as `schema_version` at batch level and is part of raw identity. Unknown versions are invalid. No CSV, XML, or connector-specific format is in v1.0.

---

# 22. Batch Model

A batch groups a coherent ingestion operation.

Conceptually:

```text
Batch
-------------------------
id
source_id
external_batch_id
schema_version
received_at
received_count
accepted_count
rejected_input_count
invalid_count
processed_count
matched_count
mismatched_count
unmatched_count
ambiguous_count
duplicate_count
failed_count
processing_state
started_at
completed_at
error_summary
```

The following counters are authoritative batch summaries written transactionally with record outcomes: `received_count`, `accepted_count`, `rejected_input_count`, `invalid_count`, `processed_count`, `matched_count`, `mismatched_count`, `unmatched_count`, `ambiguous_count`, `duplicate_count`, and `failed_count`. `received_count = accepted_count + rejected_input_count`; `processed_count = matched_count + mismatched_count + unmatched_count + ambiguous_count + duplicate_count + invalid_count`; failed records are included in `failed_count` and excluded from `processed_count` until a later attempt classifies them. Reporting views may cache these counters but may not author them.

An input becomes an accepted raw record once its envelope is parseable, source and batch are known, and its original payload is durably stored. Malformed payloads that cannot be parsed into a raw envelope are stored as `INVALID` raw submissions with a payload/error envelope when possible; if no envelope can be persisted, the batch records a rejected-input count and error evidence. Invalid records receive no canonical transaction, never enter matching, and produce an `INVALID` reconciliation outcome only when a raw record exists.

A batch provides operational boundaries for:

- replay
- reporting
- processing
- verification
- failure recovery

---

# 23. Batch State Machine

```text
             ┌──────────────┐
             │   RECEIVED   │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  VALIDATING  │
             └──────┬───────┘
               ┌────┴────┐
               ▼         ▼
          REJECTED     VALIDATED
                         │
                         ▼
                    PROCESSING
                         │
                ┌────────┼────────┐
                ▼        ▼        ▼
           COMPLETED   FAILED   PARTIAL
```

Retry/reprocessing must create explicit processing attempts rather than silently changing history.

Allowed transitions are:

| From | To | Preconditions |
|---|---|---|
| RECEIVED | VALIDATING | batch accepted with schema version |
| VALIDATING | REJECTED | batch-level schema failure |
| VALIDATING | VALIDATED | all records classified and raw evidence persisted |
| VALIDATED | PROCESSING | processing attempt created |
| PROCESSING | COMPLETED | all records reach terminal outcomes and counters reconcile |
| PROCESSING | PARTIAL | some records terminal, some explicitly failed |
| PROCESSING | FAILED | attempt fails before complete classification |
| FAILED | PROCESSING | new attempt created; prior attempt retained |
| PARTIAL | PROCESSING | new attempt created for failed/unprocessed records |

`RECEIVED`, `VALIDATING`, and `VALIDATED` are non-terminal. `COMPLETED`, `REJECTED`, `FAILED`, and `PARTIAL` are terminal for an attempt; `FAILED` and `PARTIAL` permit a new attempt without mutating prior attempt history. No other transitions are legal. Every transition emits an audit event in the same transaction as the batch-state write.

---

# 24. Reconciliation State Machine

```text
                    ┌─────────────┐
                    │   CREATED   │
                    └──────┬──────┘
                           │
                           ▼
                     EVALUATING
                           │
     ┌──────────┬──────────┼──────────┬──────────┬──────────┬──────────┐
     ▼          ▼          ▼          ▼          ▼          ▼          ▼
 MATCHED   MISMATCHED UNMATCHED_A UNMATCHED_B AMBIGUOUS DUPLICATE INVALID
                │          │          │          │
                ▼          │          │          ▼
           DISCREPANCY    FINAL      FINAL  DISCREPANCY
                │                               │
                ▼                               ▼
             RESOLVED                         RESOLVED
                │                               │
                └──────────────┬────────────────┘
                               ▼
                              FINAL
```

The complete outcome transition from `EVALUATING` is exactly one of `MATCHED`, `MISMATCHED`, `UNMATCHED_A`, `UNMATCHED_B`, `AMBIGUOUS`, `DUPLICATE`, or `INVALID`. `MATCHED`, `UNMATCHED_A`, `UNMATCHED_B`, `DUPLICATE`, and `INVALID` are terminal outcomes. `MISMATCHED` and `AMBIGUOUS` create a `Discrepancy` entity and may transition to `RESOLVED` only through an authorized resolution. `RESOLVED` is terminal for that reconciliation version.

In the diagram, `FINAL` is shorthand for a terminal outcome/version and is not an additional persisted state.

Reconciliation transition contract:

| From | To | Preconditions |
|---|---|---|
| CREATED | EVALUATING | canonical inputs and candidate snapshot are available |
| EVALUATING | MATCHED | one unique conflict-free proposal and all comparisons pass |
| EVALUATING | MISMATCHED | one unique proposal and amount, currency, or direction fails |
| EVALUATING | UNMATCHED_A / UNMATCHED_B | no proposal for the corresponding side |
| EVALUATING | AMBIGUOUS | multiple candidates satisfy the highest applicable rule |
| EVALUATING | DUPLICATE | duplicate fingerprint or 1:1 conflict component exists |
| EVALUATING | INVALID | validation produced an invalid raw record |
| MISMATCHED / AMBIGUOUS | RESOLVED | authorized resolution and discrepancy transition succeed |

No other reconciliation transition is legal. Each transition creates the immutable version and its audit event atomically.

Late arrival or correction never mutates a prior version. It creates a new reconciliation version linked by `supersedes_reconciliation_id`; the prior version remains terminal and visible.

## 24.1 Discrepancy and Resolution lifecycle

`Discrepancy` is an authoritative entity created for `MISMATCHED` or `AMBIGUOUS` outcomes. Its states are `OPEN`, `DEFERRED`, `RESOLVED`, and `REJECTED`. Allowed transitions are `OPEN → DEFERRED`, `OPEN → RESOLVED`, `OPEN → REJECTED`, and `DEFERRED → RESOLVED|REJECTED`. `RESOLVED` and `REJECTED` are terminal.

`Resolution` is an immutable decision entity, not a state. Its `resolution_type` is `AUTOMATIC`, `MANUAL_APPROVED`, `REJECTED`, or `DEFERRED`. Automatic resolutions are limited to deterministic configured rules; manual resolutions require the v1.0 authorized actor `reconciliation_operator`. Every resolution references exactly one discrepancy and one prior reconciliation version.

`DEFERRED` and `REJECTED` resolutions leave the reconciliation outcome unchanged while making the discrepancy terminal according to its lifecycle; only an approved resolution creates the reconciliation `RESOLVED` state.

## 24.2 ProcessingAttempt lifecycle

`ProcessingAttempt` states are `CREATED → RUNNING → COMPLETED|FAILED|TIMED_OUT|CANCELLED`. Only `CREATED` may transition to `RUNNING`; terminal states cannot transition. A retry creates a new attempt with `retry_of_attempt_id` and the same parent batch. Timeout and cancellation are explicit terminal failures and never imply successful business completion.

---

# 25. Matching Semantics

The initial matching system uses deterministic rule evaluation.

Each rule has:

```text
Rule
-------------------------
rule_id
version
priority
candidate_requirements
comparison_logic
enabled
```

Example conceptual hierarchy:

```text
Rule 1: exact trusted cross-reference
Rule 2: exact normalized reference
Rule 3: exact amount + currency + bounded date
Rule 4: exact amount + currency + secondary deterministic attributes
```

Rules must be ordered and versioned.

A matching result must identify the rule that produced it.

---

# 26. One-to-One Constraint

For v1.0:

```text
A1 ─────────► B1
```

is valid.

But:

```text
A1 ──────┬──► B1
         └──► B2
```

is not valid as a final 1:1 reconciliation.

Likewise:

```text
A1 ──► B1
A2 ──► B1
```

is invalid unless the duplication/reconciliation policy explicitly classifies it.

The engine must enforce this constraint rather than merely document it.

## 26.1 Deterministic conflict algorithm

1. Generate one proposal per side using the matching rules and the deterministic candidate order.
2. Build a bipartite proposal graph keyed by canonical IDs.
3. If any canonical ID has degree greater than one, mark the entire connected conflict component `DUPLICATE`; do not select a winner.
4. Otherwise, persist the unique pair as `MATCHED` or `MISMATCHED` according to reconciliation comparisons.

Records with no proposal are classified `UNMATCHED_A` or `UNMATCHED_B`; records with multiple candidates under the highest applicable rule are `AMBIGUOUS` before graph construction. Components and proposals are processed in ascending canonical-ID order, so results are independent of process or database retrieval order. The complete proposal graph is retained as evidence.

---

# 27. Corrections and Versioning

Raw records are immutable.

If a source sends a correction:

```text
Original RawRecord
       │
       ▼
Correction / supersession
       │
       ▼
New RawRecord
       │
       ▼
New CanonicalTransaction version
```

The original remains available.

This allows LEDGER to answer:

> What did the source originally send?

and:

> What is the current interpreted representation?

without rewriting history.

---

# 28. Late-Arriving Data

A counterpart may arrive after the original reconciliation attempt.

Example:

```text
Day 1
A17 → UNMATCHED_A

Day 2
B93 arrives

       │
       ▼

Candidate generation
       │
       ▼
A17 ↔ B93
       │
       ▼
Reconciliation reevaluated
```

Late arrival must not silently mutate an unrelated historical record.

The system must preserve:

- original outcome
- new processing event
- new evidence
- resulting state

Late arrival means a valid raw record for a batch or source transaction is first accepted after a prior reconciliation version for the relevant scope reached a terminal outcome. The new record may be evaluated against eligible prior records within the same source pair and configured date window. It creates a new reconciliation version; it never reopens or overwrites the old version. `current_state` is the latest non-superseded version by monotonically increasing `reconciliation_version`.

A correction is a new raw record for an existing `(source_id, source_record_id)` whose payload differs from the prior raw identity. A late arrival has a new source-native record identity; a correction reuses the source-native identifier but never the raw identity. Corrections carry their supersession lineage on the raw record (`supersedes_raw_record_id`, §27) and on the canonical transaction (`supersedes_canonical_id`, §27); the reconciliation consequence of a correction is governed by the single reconciliation-supersession rule below, exactly as for any other re-evaluation.

## 28.1 Reconciliation version supersession rule (LA-1)

This is the single authoritative rule for when a reconciliation version supersedes another. It applies to late arrivals, re-evaluations, and any other new decision.

The **participant set** of a reconciliation version is the set of its non-null canonical transaction identifiers (`source_a_record_id`, `source_b_record_id`).

1. A decision whose participant set is empty — a raw-only `INVALID` decision — never supersedes another version and is always version 1.
2. Re-evaluating an identical decision (same participants, raw record, outcome, and rule version) is idempotent: it returns the existing version and creates no new row.
3. Otherwise the new decision supersedes every *current* version whose participant set is a **subset** of the new decision's participant set. The new `reconciliation_version` is the superseded version's `reconciliation_version` plus one, and `supersedes_reconciliation_id` links the new row to it. If more than one current version qualifies, the highest `(reconciliation_version, reconciliation_id)` is linked deterministically.
4. Superseded versions are immutable and remain retrievable, but they are excluded from `current_state`.
5. A re-evaluation that does not extend its participant scope — for example a correction that introduces a new canonical version alongside the superseded one — does not supersede an unrelated version under this rule; it creates a new immutable decision version.

The canonical late-arrival case is `{A17} → {A17, B93}`: the singleton `UNMATCHED_A` version is superseded by the two-participant `MATCHED` version 2.

**Known limitation (tracked, not a silent deviation):** superseded canonical versions remain part of the candidate and matching graph, so a corrected source record can still be re-evaluated and produce additional immutable decision rows. Excluding superseded canonical versions from candidate generation is a separate, open design decision and is not implied by LA-1.

---

# 29. Idempotency

LEDGER must be safe to retry.

Important operations:

| Operation | Requirement |
|---|---|
| Batch submission | Idempotent |
| Raw record ingestion | Idempotent |
| Normalization | Deterministic |
| Candidate generation | Repeatable |
| Matching | Deterministic |
| Reconciliation | Idempotent for same version/input |
| Resolution | Explicitly controlled |
| Audit event creation | Exactly-once logical event identity |

Idempotency keys and deterministic fingerprints should be used where appropriate.

---

# 30. Consistency Model

The initial architecture favors a strongly consistent authoritative data store.

Business state should be committed transactionally where related state must remain consistent.

For example:

```text
Create reconciliation
       +
Create discrepancy
       +
Create audit event
```

should not leave the system in a state where the reconciliation exists but the corresponding authoritative audit record does not.

Derived projections may be eventually consistent.

Therefore:

```text
Authoritative state → strong consistency
Projections         → eventual consistency acceptable
Metrics              → observational, not authoritative
```

---

# 31. Failure Semantics

## Input failure

Invalid input is classified, preserved, and reported.

## Duplicate submission

Existing identity is returned/reused rather than creating duplicate state.

## Processing failure

Processing attempt becomes failed and can be retried.

## Worker/process restart

Completed authoritative work is not repeated incorrectly.

## Database failure

The operation either commits atomically or does not become authoritative.

## Partial batch failure

Successfully committed records remain visible; failed records retain explicit failure state.

## Matching failure

No match is preferable to an invented match.

---

# 32. Processing Attempt Model

Processing attempts provide operational recovery without corrupting business state.

```text
Batch
 │
 ├── Attempt 1 → FAILED
 │
 ├── Attempt 2 → FAILED
 │
 └── Attempt 3 → COMPLETED
```

Attempts should record:

- attempt ID
- batch ID
- processing version
- start time
- end time
- status
- error information
- counters

This enables reproducibility and operational diagnosis.

---

# 33. Data Storage Architecture

The initial architecture should use a durable relational store as the authoritative system of record.

Conceptually:

```text
                 ┌─────────────────────┐
                 │   Authoritative DB   │
                 ├─────────────────────┤
                 │ sources             │
                 │ batches             │
                 │ raw_records         │
                 │ canonical_records   │
                 │ candidates          │
                 │ reconciliations     │
                 │ discrepancies        │
                 │ resolutions         │
                 │ audit_events        │
                 │ processing_attempts │
                 └──────────┬──────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
           API          Reporting       Metrics
```

A separate object store may later hold large raw payloads if required.

The architecture does not require a distributed database for v1.0.

---

# 34. Performance Architecture

LEDGER must avoid algorithms whose normal behavior becomes quadratic with dataset size.

The core principle is:

```text
Raw Records
    │
    ▼
Normalization
    │
    ▼
Indexed Candidate Generation
    │
    ▼
Small Candidate Sets
    │
    ▼
Deterministic Matching
```

rather than:

```text
Every A × Every B
```

Initial performance evaluation should measure:

- ingestion records/sec
- normalization records/sec
- candidate generation throughput
- matching throughput
- reconciliation throughput
- end-to-end batch latency
- peak memory
- database write throughput
- candidate-set size distribution

The first benchmark target should be established against a known machine profile and representative dataset rather than selecting an arbitrary SLO without evidence.

Layer 13 must provide a benchmark harness that records dataset manifest and checksum, machine/OS/runtime/database profile, warm-up iterations (at least one), measured iterations (at least five), median and p95 latency, throughput, peak memory, candidate-set distribution, and correctness comparison against the unoptimized deterministic pipeline. Numerical SLOs remain intentionally deferred under D-009; no performance claim is valid without this evidence.

The Layer 13 harness is `benchmarks/run_performance.py`; its methodology is documented in
`docs/performance.md` and the latest reproducible baseline is stored in
`evidence/performance-baseline.json`.

---

# 35. Security Architecture

LEDGER may process sensitive financial information.

Security boundaries include:

```text
External User
      │
      ▼
 Authentication
      │
      ▼
 Authorization
      │
      ▼
 API
      │
      ▼
 Domain Services
      │
      ▼
 Authoritative Storage
```

Requirements include:

- authenticated access
- authorization around source/batch/reconciliation data
- least privilege
- input validation
- secrets outside source code
- protected database credentials
- audit logging
- controlled exports
- sensitive data minimization
- secure deployment configuration

No sensitive field should appear in logs unless explicitly required.

Security ownership is layered. Foundation owns secret/configuration boundaries and secure defaults. Raw ingestion and validation own untrusted-input validation and payload-size/type limits. API + Reporting owns authentication integration, authorization checks, source/batch/reconciliation scoping, controlled exports, and audit-access checks. Persistence owns least-privilege database credentials and write/read separation. Observability owns redaction enforcement. Failure Verification tests each boundary; no single layer may defer all security work to the API.

---

# 36. Observability

Observability is part of the architecture.

Every processing operation should expose:

### Metrics

- records received
- records accepted
- records rejected
- records normalized
- candidates generated
- matches
- mismatches
- ambiguous results
- duplicates
- unmatched records
- processing duration
- throughput
- retry count
- failure count

### Structured logs

Logs should contain correlation identifiers such as:

```text
batch_id
attempt_id
record_id
reconciliation_id
```

### Health

The system should expose operational health for:

- application
- database
- processing pipeline
- background processing where applicable

Foundation establishes the structured telemetry interface and redaction policy. Each processing layer emits its domain counters and correlation fields; API + Reporting exposes read-only health and metrics views; Failure Verification exercises telemetry on retries and failures. Metric names use the `ledger.<stage>.<event>` convention, labels are bounded (`source_id`, `outcome`, `schema_version`), and raw payloads, descriptions, and credentials are never metric labels. Readiness means the application and authoritative database are available; liveness means the process is responsive. Operational errors include `batch_id` and `attempt_id` where available.

---

# 37. API Boundary

The API should expose business operations rather than storage internals.

Conceptual endpoints:

```text
POST   /sources
POST   /batches
GET    /batches/{id}
GET    /batches/{id}/status

GET    /reconciliations
GET    /reconciliations/{id}

GET    /discrepancies
GET    /discrepancies/{id}

POST   /discrepancies/{id}/resolve

GET    /audit/{entity_type}/{entity_id}
```

The API must not allow callers to directly mutate authoritative reconciliation state in ways that bypass domain rules.

The v1.0 API accepts an externally configured bearer-token verifier; token contents are not persisted as business state. The only resolution role is `reconciliation_operator`. Authorization is checked against source, batch, discrepancy, and audit subject scope before the application service is called. Authentication failures return no business data; authorization failures are audited without exposing sensitive payloads.

---

# 38. Projection Architecture

The UI/reporting layer should consume derived views.

```text
                   Authoritative DB
                         │
                ┌────────┴────────┐
                ▼                 ▼
          Query Services      Projection Jobs
                │                 │
                ▼                 ▼
              API             Reporting
                │
                ▼
            Dashboard
```

The dashboard is not the source of truth.

Projections and exports are read-only, rebuildable representations derived from authoritative records and audit events. They may be eventually consistent, must record a source watermark, and may be discarded and rebuilt without loss of business state. Projection refresh, invalidation, and export generation emit telemetry but never write reconciliation, discrepancy, resolution, or raw-record authority.

---

# 39. Processing Architecture

The initial implementation should favor a controlled pipeline runner. The authoritative lifecycle is:

```text
Batch
 │
 ▼
Ingest
 │
 ▼
Validate
 │
 ▼
Normalize
 │
 ▼
Identify
 │
 ▼
Generate Candidates
 │
 ▼
Match
 │
 ▼
Reconcile
 │
 ▼
Create discrepancy
 │
 ▼
Apply authorized resolution where requested
 │
 ▼
Audit the reconciliation, discrepancy, resolution, and attempt transitions transactionally
 │
 ▼
Project
```

Each stage should expose explicit input/output contracts.

Stages may initially execute in one process while retaining boundaries that allow future parallelization.

**Operator execution rule (resolved, EMM-110).** The controlled pipeline runner is
an **out-of-band operator entrypoint**, not an HTTP operation. The HTTP service
is the data plane: `POST /v1/batches` and `POST /v1/batches/{batch_id}/records`
create and preserve raw evidence and never advance a batch. Batch progression is
performed by the published runner `python -m ledger.pipeline process`, which
selects batches by id or by state, is idempotent on re-run, records an explicit
`processing_attempts` row for every run, and reports failures through explicit
batch states (`FAILED`/`PARTIAL`, or an unchanged retryable state when
validation itself did not complete) plus a non-zero exit code. There is no
second processing rule: no HTTP processing trigger exists in v1.0, and the
dashboard reads state rather than starting work. A late arrival arrives as a new
batch; matching re-evaluates and supersedes the affected decision under LA-1
while earlier batch summaries remain historical.

---

# 40. Pipeline Checkpointing

Long-running processing should be restartable.

Conceptually:

```text
Batch 42

Ingest       ✓
Validate     ✓
Normalize    ✓
Identity     ✓
Candidates   ✓
Matching     ✗
Reconcile    -
Audit        -
Project      -
```

A restart should not require blindly repeating every earlier stage.

Checkpointing must never violate idempotency.

---

# 41. Configuration and Rule Versioning

Matching behavior must be versioned.

A reconciliation result should be explainable against the exact rules used to produce it.

Example:

```text
matching_policy = "standard_v1"
normalization_version = "canonical_v2"
```

If rules change:

```text
standard_v1
       │
       ▼
standard_v2
```

old results remain attributable to v1.

Reprocessing under v2 is a new processing operation.

---

# 42. Architectural Decision: Modular Monolith First

LEDGER v1.0 should initially be implemented as a modular system rather than a collection of distributed services.

Recommended logical modules:

```text
ledger/
├── ingestion
├── validation
├── normalization
├── identity
├── candidates
├── matching
├── reconciliation
├── resolution
├── audit
├── reporting
└── observability
```

These are **architectural boundaries**, not necessarily network boundaries.

Distribution can be introduced later if evidence demonstrates the need.

---

# 43. Technology-Neutral Dependency Direction

The dependency direction should resemble:

```text
Interfaces
    │
    ▼
Application Services
    │
    ▼
Domain
    │
    ▼
Persistence Abstractions
    │
    ▼
Infrastructure
```

Persistence abstractions are ports owned by the application boundary and consumed by application services; the domain model remains persistence-agnostic. Infrastructure implements those ports. Domain code may define pure value-object and repository-port interfaces only when they contain no storage semantics. No layer may import a concrete database, HTTP framework, CLI, dashboard, or connector.

Domain logic must not depend directly on:

- HTTP framework
- database implementation
- CLI framework
- dashboard
- external connector

This keeps reconciliation rules independently testable.

---

# 44. Domain vs Infrastructure

## Domain owns

- transaction semantics
- matching rules
- reconciliation outcomes
- state transitions
- invariants
- discrepancy semantics
- resolution rules

## Infrastructure owns

- database access
- file storage
- HTTP
- authentication mechanism
- scheduling
- logging implementation
- metrics implementation
- external connectors

This prevents infrastructure choices from becoming domain rules.

---

# 45. Core Invariants

The following invariants are mandatory.

### L-INV-001 — Raw immutability

Accepted raw input cannot be modified.

### L-INV-002 — Deterministic normalization

Same raw input + same normalization version produces the same canonical representation.

### L-INV-003 — Deterministic identity

Identity generation is stable for the same defined inputs.

### L-INV-004 — Idempotent ingestion

Retrying the same input does not create duplicate authoritative records.

### L-INV-005 — No silent loss

Every accepted input ends in an explicit processing state.

### L-INV-006 — Explainable reconciliation

Every reconciliation decision has identifiable inputs, rules, and evidence.

### L-INV-007 — No automatic ambiguous match

Ambiguous candidates cannot become MATCHED without an explicit deterministic resolution rule or authorized resolution.

### L-INV-008 — Audit preservation

Authoritative decisions and significant transitions have corresponding audit evidence.

### L-INV-009 — 1:1 enforcement

A final v1.0 reconciliation cannot violate the one-to-one constraint.

### L-INV-010 — Historical preservation

Corrections do not erase prior source evidence or decision history.

### L-INV-011 — State-machine validity

Illegal state transitions are rejected.

### L-INV-012 — Source identity isolation

A source-native identifier cannot be assumed to identify the same transaction across independent sources.

## 45.1 Invariant ownership and evidence

| Invariant | Owner | Enforcement | Verification | Evidence |
|---|---|---|---|---|
| L-INV-001 | Ingestion/Persistence | immutable raw writes and correction links | V3/V4 | raw payload, write rejection, correction chain |
| L-INV-002 | Normalization | versioned deterministic mapper | V2/V5 | canonical fixture and fingerprint |
| L-INV-003 | Identity | canonical serialization and SHA-256 IDs | V2/V4 | identity vectors |
| L-INV-004 | Ingestion/Persistence | operation/raw uniqueness constraints | V3/V4 | retry and duplicate-submission result |
| L-INV-005 | Batch/Pipeline | accepted/rejected/terminal counters and states | V3/V4/V5 | batch ledger and per-record outcome |
| L-INV-006 | Matching/Reconciliation | rule/version/input/evidence fields | V2/V3/V5 | proposal and decision evidence |
| L-INV-007 | Matching/Resolution | ambiguity branch and authorized resolution | V2/V4/V5 | candidate set and resolution audit |
| L-INV-008 | Audit/Persistence | append-only unique events in same transaction | V3/V4/V5 | event IDs/sequences and rollback result |
| L-INV-009 | Matching/Reconciliation | proposal conflict graph with no automatic winner | V2/V3/V4 | conflict component evidence |
| L-INV-010 | Versioning/Resolution | immutable superseding versions | V4/V5 | original/current version chain |
| L-INV-011 | Domain | transition guards and terminal-state rules | V2/V4 | legal/illegal transition tests |
| L-INV-012 | Identity | namespaced source IDs and pair-only cross-source identity | V2/V3 | namespace isolation fixtures |

---

# 46. Verification Architecture

Verification is designed into the system rather than added after implementation.

```text
                  LEDGER Verification
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
     Static            Tests            Runtime
        │                │                │
   type/lint        unit/integration   failure tests
                         │                │
                         └───────┬────────┘
                                 ▼
                           Product Proof
```

## V1 — Static

- type checks
- lint
- formatting
- dependency checks
- architecture checks

## V2 — Unit

Test:

- normalization
- identity
- candidate generation
- matching
- state transitions
- reconciliation rules

## V3 — Integration

Test:

- ingestion → database
- pipeline stages
- reconciliation persistence
- audit creation
- API/reporting

## V4 — Failure

Inject:

- duplicate submission
- malformed records
- process restart
- database interruption
- partial batch failure
- late-arriving record
- ambiguous candidates
- duplicate source records
- matching-rule failure

## V5 — Product proof

Demonstrate:

```text
Messy Source A
       +
Messy Source B
       │
       ▼
Canonicalization
       │
       ▼
Candidate Generation
       │
       ▼
Deterministic Matching
       │
       ▼
Reconciliation
       │
       ▼
Discrepancy
       │
       ▼
Resolution
       │
       ▼
Audit Evidence
```

---

# 47. Portfolio-Grade Proof Scenario

The canonical demonstration should contain deliberately imperfect data.

Example:

```text
Source A
────────────────────────────
A001  $100.00  Sep 01
A002  $250.00  Sep 02
A003  $500.00  Sep 03
A004  $100.00  Sep 03
A005  malformed

Source B
────────────────────────────
B991  $100.00  Sep 01
B992  $250.00  Sep 02
B993  $700.00  Sep 03
B994  $100.00  Sep 03
B995  $100.00  Sep 03
```

Expected behavior should demonstrate several classes:

```text
A001 ↔ B991       MATCHED
A002 ↔ B992       MATCHED
A003              UNMATCHED_A
A004 ↔ B994/B995  AMBIGUOUS
A005              INVALID
B993              UNMATCHED_B
```

The proof interpretation is deterministic: A003 has no eligible counterpart because the only same-date B record has a different amount, so it is `UNMATCHED_A`, not `MISMATCHED`. A mismatched case is demonstrated separately by adding `A006` and `B996` with the same transaction reference but different amounts; that pair is `MISMATCHED` under M-001.

The proof must capture, for each record, source payload, raw identity, validation result, canonical identity/version, candidate list in canonical-ID order, selected rule or failure, reconciliation outcome, discrepancy/resolution identifiers where applicable, audit event IDs, and correlation IDs. The duplicate scenario uses two distinct source IDs with identical canonical payloads and must produce `DUPLICATE`; resubmitting the same batch must produce `SUBMISSION_DUPLICATE` telemetry without a new raw or reconciliation record. A late-arriving record creates a new reconciliation version, and a correction creates a new raw/canonical/reconciliation version linked by supersession.

Then introduce:

- duplicate submission
- late-arriving record
- corrected record
- processing restart

and demonstrate that LEDGER remains correct and explainable.

---

# 48. Evidence Model

A successful portfolio demonstration should produce evidence such as:

```text
Architecture diagram
       +
Sample source files
       +
Pipeline execution logs
       +
Reconciliation results
       +
Failure injection
       +
Recovery evidence
       +
Benchmark results
       +
Audit trail
```

The repository should allow another engineer to reproduce the demonstration.

---

# 49. Scaling Strategy

LEDGER v1.0 deliberately starts with a single authoritative data store and modular processing.

Scaling should proceed only when measurements justify it.

Potential future evolution:

```text
v1.0
Modular single-node pipeline
        │
        ▼
v1.x
Parallel batch processing
        │
        ▼
v2.x
Distributed workers
        │
        ▼
Future
Partitioned / streaming reconciliation
```

The architecture must not claim distributed scalability merely because distributed components could theoretically be added.

---

# 50. Architectural Tradeoffs

## Deterministic matching over ML

Chosen because:

- reproducibility matters
- explanations matter
- false positives are costly
- verification is easier

ML/fuzzy matching may become an experimental extension later.

## Relational authority over distributed storage

Chosen because:

- relationships are central
- reconciliation requires transactional consistency
- queryability matters
- operational complexity stays bounded

## Modular monolith over microservices

Chosen because:

- LEDGER is a portfolio project
- correctness is the primary signal
- distributed deployment adds complexity without immediate product value

## Immutable evidence over mutable records

Chosen because:

- auditability matters
- corrections must remain explainable
- debugging requires historical truth

---

# 51. Architectural Decisions

The following decisions are resolved for v1.0. Numerical performance SLOs remain deferred by design.

### D-001 — Exact canonical fields — RESOLVED

Use the fields and fixed-point/UTC semantics in §21. Amounts are exact Decimal(20,4); canonical records are immutable versions.

### D-002 — Source schemas — RESOLVED

Use `source_a.v1` and `source_b.v1` exactly as defined in §21.1.

### D-003 — Matching rules — RESOLVED

Use M-001 and M-002 in §25 under immutable policy `standard_v1`.

### D-004 — Date tolerance — RESOLVED

Inclusive plus or minus 2 UTC calendar days.

### D-005 — Amount tolerance — RESOLVED

Amounts must be exactly equal as fixed-point decimals; no tolerance in v1.0.

### D-006 — Currency behavior — RESOLVED

Currency must be equal ISO-4217 code; cross-currency reconciliation is prohibited.

### D-007 — Late-arrival semantics — RESOLVED

Late arrivals create new reconciliation versions and never reopen or overwrite prior versions. The exact scope and versioning rule is LA-1 in §28.1. No legacy or conflicting late-arrival rule exists.

### D-008 — Resolution authority — RESOLVED

Automatic deterministic resolutions are policy-defined; manual resolutions require the authorized actor `reconciliation_operator`.

### D-009 — Benchmark target — DEFERRED

Layer 13 must capture the benchmark evidence contract in §34. Numerical SLOs are not defined until representative measurements exist.

### D-010 — Initial interface — RESOLVED

The first interface is a local JSON/CLI pipeline runner for Layers 1-11 and an HTTP API for Layer 12 reporting and authorized resolution operations. Query/reporting and export operations are read-only; resolution is the only API mutation and must pass domain authorization. No external connector is in v1.0.

### D-011 — Duplicate taxonomy — RESOLVED

Submission duplicates are idempotent ingestion replays; business duplicates are canonical-fingerprint duplicates or 1:1 proposal conflicts (§14.1).

### D-012 — Current-state derivation — RESOLVED

Versioned authoritative records are immutable. Current state is the latest non-superseded version by monotonic version number; projections are derived from that state.

### D-013 — Security and observability ownership — RESOLVED

Responsibilities and verification owners are defined in §§35-36 and Section 52 prompt contracts.

### D-014 — Database recovery objectives (RPO/RTO) — RESOLVED

Approved for v1.0 (Epic 5 / EMM-108). This is a data-recovery policy and is
distinct from the performance SLOs still deferred by D-009.

- **Backup cadence:** one verified full snapshot every 15 minutes to local
  persistent storage (24 hour retention), plus one daily snapshot replicated
  offsite (30 day retention). A snapshot that fails verification does not count
  as a recovery point; the previous verified snapshot does.
- **RPO ≤ 15 minutes.** At most the transactions committed since the last
  successful verified snapshot may be lost.
- **RTO ≤ 30 minutes.** Time from failure detection to a verified, serving
  database restored from the most recent verified snapshot, including operator
  action, restore, verification, and service start. The measured drill path must
  stay inside this budget with margin.
- **SQLite single-writer boundary accepted.** The single authoritative SQLite
  store (§ persistence layer, `docs/database-operations.md` §1) satisfies these
  targets at the v1.0 scale; the targets do not force a database-boundary
  architecture change. Reassess if a later decision reverses the single-writer
  or backup strategy.

Backup scheduling, offsite replication, backup-failure alerting, and staging
restore rehearsals are deployment and observability obligations owned by the
production-readiness epics that follow Epic 5.

---

# 52. Recommended Implementation Layers

The implementation plan should follow this order. These are repository-control layers, not a second business pipeline; each maps to one or more architectural stages above.

```text
LAYER 1 — Foundation
        │
        ▼
LAYER 2 — Domain Model
        │
        ▼
LAYER 3 — Persistence
        │
        ▼
LAYER 4 — Raw Ingestion
        │
        ▼
LAYER 5 — Validation
        │
        ▼
LAYER 6 — Normalization
        │
        ▼
LAYER 7 — Identity
        │
        ▼
LAYER 8 — Candidate Generation
        │
        ▼
LAYER 9 — Matching
        │
        ▼
LAYER 10 — Reconciliation
        │
        ▼
LAYER 11 — Resolution + Audit
        │
        ▼
LAYER 12 — API / Reporting
        │
        ▼
LAYER 13 — Performance
        │
        ▼
LAYER 14 — Failure Verification
        │
        ▼
LAYER 15 — Product Proof
```

Each implementation layer should have:

- objective
- dependencies
- scope
- allowed changes
- forbidden changes
- contracts
- acceptance criteria
- verification
- evidence
- exit condition

---

# 53. Definition of Architectural Completion

Architecture v1.0 is considered ready for implementation when another engineer can answer all of these without guessing:

1. What is LEDGER?
2. What is a transaction?
3. What does reconciliation mean?
4. What states can a record occupy?
5. Who owns each state?
6. What data is immutable?
7. How is identity established?
8. How are candidates generated?
9. How is matching decided?
10. What happens when matching is ambiguous?
11. How are duplicates handled?
12. What happens when data arrives late?
13. How are corrections represented?
14. What happens when processing fails?
15. What makes ingestion idempotent?
16. How is every decision explained?
17. What is authoritative versus derived?
18. How is the system verified?
19. What does success look like?
20. What evidence proves the system works?

If these answers are explicit, implementation can proceed without repeatedly redesigning the system.

---

# 54. Final Architectural Model

The complete LEDGER architecture can be reduced to four fundamental ideas:

```text
                ┌────────────────────┐
                │    SPECIFICATION   │
                │ What must be true  │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │    ARCHITECTURE    │
                │ Who owns what      │
                │ How state moves    │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │    IMPLEMENTATION  │
                │ Controlled layers  │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │      EVIDENCE      │
                │ Does it actually   │
                │ work as designed?  │
                └────────────────────┘
```

LEDGER should not be considered complete because the pipeline executes successfully.

It is complete when the implementation conforms to the architecture, the invariants hold under normal and failure conditions, reconciliation decisions are explainable, and the product behavior is demonstrated with reproducible evidence.

---

## Status

**Architecture:** v1.0 baseline  
**Implementation status:** Layers 1-15 implemented and verified  
**Completed:** Layers 1-15: Foundation, Domain Model, Persistence, Raw Ingestion, Validation, Normalization, Identity, Candidate Generation, Matching, Reconciliation, Resolution + Audit, API + Reporting, Performance, Failure Verification, Product Proof  
**Current implementation frontier:** Layers 1-15 complete; no post-Layer-15 implementation layer is authorized  
**Not implemented:** post-Layer-15 scope (by instruction)

### Repository implementation evidence

- Foundation configuration and telemetry live in `src/ledger/config.py` and `src/ledger/observability.py` and are covered by `tests/test_foundation.py`.
- The infrastructure-independent domain model lives in `src/ledger/domain/` and is covered by `tests/test_domain_model.py`.
- Relational persistence lives in `src/ledger/persistence/sqlite.py` and is covered by `tests/test_persistence.py`.
- Raw ingestion, validation, normalization, identity, and candidate generation live in `src/ledger/ingestion.py`, `src/ledger/validation.py`, `src/ledger/normalization.py`, `src/ledger/identity.py`, and `src/ledger/candidates.py`, with focused coverage in `tests/test_ingestion.py`, `tests/test_validation.py`, `tests/test_normalization.py`, `tests/test_identity.py`, and `tests/test_candidates.py`.
- Deterministic matching lives in `src/ledger/matching.py` with focused coverage in `tests/test_matching.py`.
- Authoritative reconciliation persistence and discrepancy creation live in `src/ledger/reconciliation.py`, with focused coverage in `tests/test_reconciliation.py`.
- Authorized discrepancy resolution and immutable audit orchestration live in `src/ledger/resolution.py`, with focused coverage in `tests/test_resolution.py`.
- Layer 13 benchmark harness, methodology, and baseline evidence live in `benchmarks/run_performance.py`, `docs/performance.md`, and `evidence/performance-baseline.json`, with a focused contract test in `tests/test_performance.py`.
- Layer 14 failure-injection and recovery evidence lives in `tests/test_failure_verification.py` and `docs/failure-verification.md`.
- Layer 15 product-proof fixtures, runner, regression tests, documentation, and evidence live in `product_proof/dataset.py`, `product_proof/runner.py`, `product_proof/run_product_proof.py`, `tests/test_product_proof.py`, `docs/product-proof.md`, and `evidence/product-proof.json`.
- The reproducible verification command is `PYTHONPATH=src python3 -m unittest discover -s tests -v`.

### State-to-audit matrix

| Authoritative operation | Required audit event | Atomicity | Retry behavior |
|---|---|---|---|
| Batch transition | `BATCH_STATE_CHANGED` | state update + audit append | existing event identity is returned |
| Processing-attempt transition | `BATCH_STATE_CHANGED` | state update + audit append | existing event identity is returned |
| Reconciliation version transition | `RECONCILIATION_CREATED` or outcome event | new immutable version + audit append | same event/version is idempotent |
| Discrepancy transition | `RESOLUTION_APPLIED` or state event | state update + audit append | existing event identity is returned |
| Resolution application | `RESOLUTION_APPLIED` | discrepancy, resolution, reconciliation version, and audits commit together | duplicate identities do not create new history |
| Raw/canonical correction or version write | ingestion/normalization event supplied by owning layer | immutable insert in caller transaction | identity uniqueness prevents duplicate authoritative rows |

### Persistence transaction and audit contract

Persistence uses one SQLite transaction per authoritative operation. Writer transactions use `BEGIN IMMEDIATE`; state writes and audit appends either both commit or both roll back. Audit sequence numbers are allocated transactionally per `(entity_type, entity_id)`. Retrying an existing `event_id` returns the original event without allocating a new sequence.

Reconciliation transitions preserve immutable history: the domain-approved next version is inserted with `supersedes_reconciliation_id`, and its audit event is appended in the same transaction. Candidate rows are rebuildable derived state, not an authority. Raw records, canonical transactions, match candidates, reconciliation versions, resolutions, and audit events are append-only; mutable batch, attempt, and discrepancy state changes only through guarded transition operations.

---

# 55. Remediation Change Log

| Decision | Change | Rationale | Affected layers | Invariants |
|---|---|---|---|---|
| R-001 | Defined exact canonical fields, source schemas, fixed-point amounts, and UTC timestamps | Remove field and schema ambiguity | 2-7 | L-INV-002, L-INV-003, L-INV-012 |
| R-002 | Defined M-001/M-002 matching, candidate completeness, and deterministic ordering | Prevent invented matching semantics | 8-10 | L-INV-006, L-INV-007, L-INV-009 |
| R-003 | Defined no-winner global 1:1 conflict handling and duplicate taxonomy | Preserve correctness under conflicts and retries | 4, 7-10 | L-INV-004, L-INV-007, L-INV-009 |
| R-004 | Defined identity, fingerprint, idempotency, correction, and audit-event algorithms | Make replay and history deterministic | 3-4, 6-7, 11, 14 | L-INV-001, L-INV-003, L-INV-004, L-INV-008, L-INV-010 |
| R-005 | Replaced prose state diagrams with legal transitions and versioned reconciliation | Make failure/retry/reopen behavior implementable | 2-3, 10-11, 14 | L-INV-005, L-INV-008, L-INV-011 |
| R-006 | Assigned security, observability, projection, and export ownership | Close cross-cutting control gaps | 1, 3-5, 12, 14-15 | L-INV-005, L-INV-006, L-INV-008 |
| R-008 | Added optional `raw_record_id` lineage to `Reconciliation`; `INVALID` outcomes are raw-only and do not require canonical transactions | Preserve validation-failure evidence through reconciliation without inventing canonical state | 10 | L-INV-001, L-INV-005, L-INV-008 |
| R-007 | Corrected and expanded the product-proof scenario | Remove A003 contradiction and require reproducible evidence | 13-15 | All invariants |
| R-009 | Fixed `LedgerAPI` dataclass conversion used by resolution responses | Product proof exposed HTTP 400 on every operator resolution: `asdict` deep-copies frozen mapping evidence; conversion now iterates dataclass fields recursively | 12, 15 | L-INV-008 |
