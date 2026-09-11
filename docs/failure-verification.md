# Layer 14 Failure Verification

Layer 14 proves LEDGER's failure semantics with automated fault injection and
retry/recovery assertions. The authoritative contract is: an operation either
commits completely or leaves authoritative state unchanged and safely retryable.

Run the focused suite:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_failure_verification.py' -v
```

Run the full regression suite with `pytest -q` or `make check`.

## Methodology

Faults are injected at real service and repository boundaries. Where possible,
the injected failure occurs only after an earlier authoritative write has
already executed, so rollback is proven rather than assumed:

- `raw_records.save` raises `sqlite3.OperationalError` to simulate a database
  interruption during ingestion.
- `audit_events.append` succeeds for the first event(s) and then raises, proving
  that a late audit failure cannot leave partial state.
- `validation_results.save`, `match_candidates.save`, `discrepancies.save`, and
  reconciliation `persist_decision` raise at controlled points after earlier
  writes in the same transaction.

Each test restores the original method, retries the same operation, and asserts
that row counts, audit event counts, batch/attempt states, and immutable history
match the deterministic retry contract. The suite covers the scenarios in the
Layer 14 prompt and complements the earlier layer-specific failure tests.

## Scenarios and observed behavior

| Boundary | Automated evidence | Expected and observed behavior |
|---|---|---|
| Ingestion database interruption | `test_database_interruption_rolls_back_ingestion_and_retry_is_idempotent` | No raw/submission/counter row remains; retry accepts once and a second retry is a duplicate submission. |
| Interrupted/partial batch | `test_interrupted_batch_retry_completes_without_duplicates_or_loss` | A committed first record remains untouched; the interrupted second record leaves no row; retry adds exactly one row and no later duplicate. |
| Validation failure and batch recovery | `test_validation_batch_failure_remains_retryable_without_duplicate_results` | Per-record validation failure leaves the batch in `VALIDATING` with no result/counter/audit for the record; retry reaches `VALIDATED` once. |
| Normalization audit failure | `test_normalization_audit_failure_rolls_back_and_retry_is_idempotent` | The canonical insert and audit roll back together; retry produces one canonical row and one event. |
| Identity/corrupt lineage | `test_identity_rejects_corrupt_lineage_without_state_change` | Corrupt canonical ID/fingerprint is rejected without any write or mutation. |
| Candidate persistence failure | `test_candidate_persistence_failure_rolls_back_batch_and_retry_is_idempotent` | A multi-candidate batch fails after the first insert and rolls back all candidates; retry persists exactly the original two candidates. |
| Reconciliation/discrepancy persistence | `test_reconciliation_discrepancy_failure_rolls_back_decision_and_retry_is_idempotent` | Discrepancy failure after the reconciliation insert rolls back the reconciliation; retry creates exactly one reconciliation/discrepancy pair. |
| Reconciliation/audit atomicity | `test_reconciliation_audit_failure_after_first_event_rolls_back_all_state` | Failing on the second audit append rolls back the reconciliation, discrepancy, and first audit; retry commits once. |
| Matching partial failure | `test_matching_partial_failure_recovers_without_duplicate_decisions` | Two of three decisions commit, the third rolls back; retry completes three decisions with no duplicates and no discrepancies. |
| Late addition/reprocessing | `test_late_reprocessing_preserves_prior_decisions_without_duplicates` | Processing a later pair after an earlier match leaves the two prior reconciliation rows byte-for-byte intact and adds exactly one new row; a further reprocessing run stays deterministic. |
| Resolution mid-commit audit failure | `test_resolution_audit_failure_after_partial_writes_rolls_back_all_state` | Failing on the third audit append after two successful appends rolls back discrepancy state, reconciliation version, resolution, and all three audits; retry commits exactly once. |
| Processing attempt failure/retry | `test_processing_attempt_failure_state_and_retry_remain_valid` | A failed terminal transition rolls back to `RUNNING`; a committed failure remains terminal while a new retry attempt completes with `retry_of_attempt_id` lineage. |
| Invalid/corrupt input | `test_invalid_and_corrupt_input_is_explicit_and_never_processed` | Rejected envelopes persist no raw record; invalid raw records are preserved, validated as invalid, and never reach canonical/candidate/reconciliation state. |
| Illegal terminal transitions | `test_terminal_states_reject_illegal_transitions_without_mutation_or_audit` | Terminal batch and attempt states reject illegal transitions before any state write or audit append. |

Existing Layer 1-13 tests additionally cover malformed schema fields, duplicate
submission replay, correction immutability, audit idempotency, batch/attempt
state machines, API authorization failures, and telemetry redaction. Together
with the suite above they exercise every critical boundary in the Layer 14
prompt without weakening an invariant.

## Limitations

- Fault injection is done at Python service/repository boundaries; it does not
  kill a real process or fill a real disk. It verifies transaction semantics,
  not OS-level durability behavior.
- Layers 1-13 do not include a full batch orchestration controller, so
  processing-attempt recovery is proven at the persistence/domain boundary and
  pipeline operations are retried per operation rather than through a workflow
  manager.
- Database update/delete immutability is enforced by SQLite triggers and is
  covered by the existing Layer 1-13 persistence tests.

No product feature, API change, performance change, or Layer 15 implementation
was introduced.
