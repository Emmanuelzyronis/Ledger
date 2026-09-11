# Layer 15 Product Proof

Layer 15 proves that the implemented LEDGER system satisfies its product
mission end to end: independently produced records are ingested, preserved,
validated, normalized, identified, candidate-generated, deterministically
matched, reconciled, resolved, audited, and reported through the real
application services and real SQLite persistence. No core pipeline component is
mocked.

Run the complete reproducible suite from the repository root:

```sh
PYTHONPATH=src python3 product_proof/run_product_proof.py
```

The runner executes every scenario on fresh databases and writes
`evidence/product-proof.json`. The focused regression suite is
`tests/test_product_proof.py`; run it with `pytest -q` or
`PYTHONPATH=src python3 -m unittest tests.test_product_proof -v`.

## Fixtures

All fixtures are deterministic payload dictionaries in `product_proof/dataset.py`
and are pinned by `manifest_sha256`
(`8902b2efb05940fcdb38bcca3c298a01e1eac69cc9bfac117321d96c100cca3e` in the
checked-in evidence). Every runner-controlled timestamp uses the fixed clock
`2026-09-08T12:00:00Z`; ingestion, validation, normalization, matching, and
resolution stages are called with that clock so decisions, identities, and
evidence are repeatable. The evidence signature covers authoritative rows and
excludes wall-clock timestamps, which are never business state.

## Scenarios and observed outcomes

### Portfolio scenario (all seven reconciliation outcomes)

Records A001-A007 and D-A1/D-A2 (`source_a.v1`) plus B991-B997 and D-B1
(`source_b.v1`) follow Architecture.md section 47. After one deterministic
pipeline run, every record reaches the expected terminal outcome:

| Record(s) | Expected | Observed | Rule / evidence |
|---|---|---|---|
| A001, B991 | MATCHED | MATCHED | M-001 reference `TX-1001` |
| A002, B992 | MATCHED | MATCHED | M-001 reference `TX-1002` |
| A003 | UNMATCHED_A | UNMATCHED_A | no eligible counterpart |
| A004, B994, B995 | AMBIGUOUS | AMBIGUOUS | M-002 amount/currency/window, candidate set preserved |
| A005 | INVALID | INVALID | validation failure; raw-only reconciliation |
| A006, B996 | MISMATCHED | MISMATCHED | M-001 reference `TX-1006`; amount differs |
| A007, B997 | MISMATCHED | MISMATCHED | M-001 reference `TX-1007`; direction differs |
| B993 | UNMATCHED_B | UNMATCHED_B | no eligible counterpart |
| D-A1, D-A2, D-B1 | DUPLICATE | DUPLICATE | one-to-many/many-to-one proposal conflict, no winner |

The initial decision rows are 13: MATCHED x2, MISMATCHED x2, UNMATCHED_A x1,
AMBIGUOUS x3, UNMATCHED_B x1, DUPLICATE x3, INVALID x1. A004/B994/B995 are
ambiguous as a component: each record's candidate set is preserved in its
decision evidence rather than silently forced into a match. The ambiguity is
symmetric because all three records share amount/currency within the two-day
date window of M-002.

### Resolution workflows

The five discrepancies (A004, A006, A007, B994, B995) demonstrate every
authorized resolution class:

| Record | Discrepancy outcome | Resolution | Actor | Result |
|---|---|---|---|---|
| A004 | AMBIGUOUS | AUTOMATIC | system | discrepancy RESOLVED; reconciliation v2 RESOLVED (supersedes v1) |
| A006 | MISMATCHED | MANUAL_APPROVED (via API) | reconciliation_operator | discrepancy RESOLVED; reconciliation v2 RESOLVED (supersedes v1) |
| A007 | MISMATCHED | DEFERRED | reconciliation_operator | discrepancy DEFERRED; reconciliation stays MISMATCHED v1 |
| B994 | AMBIGUOUS | REJECTED | reconciliation_operator | discrepancy REJECTED; reconciliation stays AMBIGUOUS v1 |
| B995 | AMBIGUOUS | left OPEN | - | residual open item visible in reporting |

Re-applying each resolution returns the identical immutable resolution without
new rows. Audit events `RESOLUTION_APPLIED` are appended for the discrepancy,
resolution, and (where approved) the superseding reconciliation version in the
same transaction.

### API, reporting, and security

- `GET /reports` and batch-scoped `GET /reports?batch_id=...` outcome counts
  agree with the authoritative reconciliation rows.
- `GET /export` is a read-only projection and contains no raw payload values.
- A reader scoped to `source-a` sees only `source-a` reconciliation rows,
  cannot read a `source-b` batch report or audit trail (403), and cannot
  resolve discrepancies (403, no operator role). Unauthenticated requests are
  rejected (401).
- The late-arriving record is ingested through `POST /batches/{id}/records`,
  and its replay returns `duplicate_submission: true` without a new raw row.

### Extensions on the same authoritative database

- Idempotent replay: re-running validation, normalization, candidate
  generation, and matching adds no raw, canonical, or reconciliation rows.
  Resubmitting an accepted payload returns `SUBMISSION_DUPLICATE` with no new
  raw row and a `SUBMISSION_DUPLICATE` audit event.
- Late arrival: `B-998` (the $500 counterpart for A003) is accepted after the
  first evaluation; re-evaluation adds one MATCHED decision for A003/B-998 at
  `reconciliation_version` 2 whose `supersedes_reconciliation_id` links to the
  original UNMATCHED_A version. The original row remains byte-for-byte intact
  and is excluded from `current_state`; replaying the evaluation adds no row.
  This is the LA-1 rule in `Architecture.md` §28.1.
- Immutability: direct `UPDATE` of an accepted raw payload is rejected by
  persistence, and the row remains intact; no authoritative row was mutated or
  deleted by replay, resolution, or late arrival.

### Correction scenario

P-1/Q-1 reconcile MATCHED first. Correcting P-1 (same `source_record_id`, new
payload, amount 120.00 -> 125.00) creates a new immutable raw record linked by
`supersedes_raw_record_id`, a new canonical version, and new decision rows.
The original raw row, canonical row, and MATCHED decision remain intact and
retrievable with validation and audit history; a pipeline replay after the
correction adds no duplicate rows.

### Restart scenario

A real SQLite file is written, closed, reopened, and the pipeline is replayed.
Row counts and the database signature are identical after the simulated
restart.

### Telemetry

Ingestion, validation, normalization, and identity emit structured telemetry
events (`ledger.ingestion.record_accepted`, `ledger.validation.record_valid`,
`ledger.normalization.completed`, `ledger.identity.verified`,
`ledger.candidates.generated`). Serialized events contain no payload or
description values.

## Invariant evidence (L-INV-001 through L-INV-012)

| Invariant | Product-proof evidence |
|---|---|
| L-INV-001 raw immutability | immutability probe rejected; raw snapshot preserved across replay/resolution/late arrival |
| L-INV-002 deterministic normalization | replay normalization returns the same canonical rows and fingerprints |
| L-INV-003 deterministic identity | identity verification stable across pipeline replay |
| L-INV-004 idempotent ingestion | service and API submission duplicates; pipeline replay adds no rows |
| L-INV-005 no silent loss | all 17 portfolio records reach an explicit outcome; every raw has a validation result |
| L-INV-006 explainable decisions | every decision row carries rule_version, outcome, candidate_order, evaluated_at; M-001 on matched/mismatched |
| L-INV-007 no automatic ambiguous match | A004/B994/B995 AMBIGUOUS with candidate sets preserved; automatic resolution requires system actor and rule_version |
| L-INV-008 audit preservation | audit stage coverage and RESOLUTION_APPLIED lineage; SUBMISSION_DUPLICATE events |
| L-INV-009 1:1 enforcement | DUPLICATE conflict components with no winner; all matches are 1:1 |
| L-INV-010 historical preservation | correction and late-arrival scenarios preserve prior rows byte-for-byte; the late-arrival version 2 links to version 1 and both are retrievable |
| L-INV-011 state-machine validity | resolution transitions follow the authorized state machine (RESOLVED v2 supersession, DEFERRED, REJECTED, OPEN); illegal transitions are rejected by the existing domain/persistence tests |
| L-INV-012 source identity isolation | cross-source matching only; API source scoping enforced |

## Verification results

- `pytest -q`: 117 passed (96 Layer 1-14 tests plus 21 product-proof / late-arrival
  regression tests).
- `make check`: 117 passed.
- `python3 -m compileall -q src tests benchmarks product_proof`: clean.
- `git diff --check`: clean.
- The product-proof suite is deterministic: two full runs produce the same
  signature (`evidence/product-proof.json` records the checked-in signature).

## Defect found and remediated

Product proof exposed one Layer 12 defect: `LedgerAPI._convert` used
`dataclasses.asdict`, which deep-copies fields and fails on the frozen
(`mappingproxy`) evidence stored on `Resolution`/`Discrepancy`/`Reconciliation`
results. Every `POST /discrepancies/{id}/resolve` therefore returned HTTP 400
("cannot pickle 'mappingproxy' object"). The fix is surgical and at the root
cause in `src/ledger/api.py`: dataclass conversion now iterates
`__dataclass_fields__` and recursively converts each field instead of calling
`asdict`. Operator resolution through the API now succeeds and is proven by
the `resolution.api_A006` check. No domain, persistence, or invariant change
was required.

## Limitations

- The signature and evidence exclude wall-clock timestamps, which are stored on
  audit rows and are not business state; all runner-controlled semantics use
  the fixed clock.
- Corrections create an immutable raw supersession chain and new canonical
  versions, but superseded canonical versions remain part of the candidate and
  matching graph. Re-evaluation therefore adds new decision rows and never
  mutates old ones; the correction scenario asserts exactly this observed
  behavior. `Architecture.md` §27 defines correction lineage at the
  raw/canonical level, and §28.1 (LA-1) defines the single reconciliation-level
  supersession rule. Excluding superseded canonical versions from candidate
  generation is a tracked, open design decision (see the project backlog), not
  an implied part of LA-1.
- Late arrivals are governed by LA-1 (`Architecture.md` §28.1): a late-arriving
  counterpart extends a previously decided scope, so the new decision supersedes
  the prior singleton version and increments `reconciliation_version`. Prior
  versions stay immutable; `current_state` is the latest non-superseded version.
- Batch counters track ingestion/validation accounting; reconciliation
  outcomes are authoritative on the reconciliations table and are verified
  against API reports there.
- The restart scenario proves connection-level reopen/replay semantics on a
  real SQLite file, not an OS process kill.
- No production readiness is claimed because product proof passes; the proof
  demonstrates the implemented product contract with reproducible evidence.
