# LEDGER Release Process (Epic 7 / EMM-83)

How a version is declared, built, verified, and evidenced. Deployment mechanics
are in `docs/deployment.md`; the go/no-go gate is `docs/release-checklist.md`.

## Versioning

`VERSION` holds the release version (`MAJOR.MINOR.PATCH`). The API contract is
versioned separately: `/v1` in `docs/openapi/ledger.v1.json` (see
`docs/api-contract.md`). A release may ship many `/v1` additions; a breaking API
change requires `/v2` and therefore a major release.

- **patch** — fixes inside existing behavior, no contract change
- **minor** — additive `/v1` operations or fields, new pipeline capability
- **major** — breaking contract change, storage-incompatible migration, or a
  reversed architecture decision (for example the D-014 recovery policy)

## Release steps

1. **Freeze.** All epic work for the version is committed and `git status` is
   clean.
2. **Verify.**
   ```sh
   make check                                   # 216 unit/integration tests
   make observability-proof                     # evidence/observability.json
   make db-drill                                # evidence/database-operations.json
   PYTHONPATH=src python3 product_proof/run_product_proof.py
   PYTHONPATH=src python3 benchmarks/run_performance.py
   ```
3. **Scan.**
   ```sh
   python3 scripts/scan.py --require-tools      # evidence/security-scan.json
   ```
4. **Build.**
   ```sh
   python3 scripts/release.py build --version "$(cat VERSION)" --output dist
   python3 scripts/release.py verify  --artifact "dist/ledger-$(cat VERSION).tar.gz"
   ```
5. **Stage.** Deploy the artifact to staging and run the staging proof
   (`docs/staging.md`). Record results in the release checklist.
6. **Go/no-go.** Complete `docs/release-checklist.md`. Every line is signed.
7. **Roll out.** Deploy the same artifact to production
   (`docs/deployment.md` §5), watch the dashboards in
   `docs/observability/ledger-overview.dashboard.json`, and keep the rollback
   command ready.
8. **Tag.** `git tag -s "v$(cat VERSION)" -m "LEDGER $(cat VERSION)"` (a human
   performs the signed tag; the agent does not create tags).
9. **Post-release review.** Record what shipped, what broke, and what is
   deferred.

## Evidence package

A release is auditable when these artifacts exist, are reproducible, and are
committed with the revision they describe:

| Evidence | Produced by |
| --- | --- |
| Unit/integration/perf results | `make check`, `benchmarks/run_performance.py` |
| Product proof | `product_proof/run_product_proof.py` → `evidence/product-proof.json` |
| Database recovery | `make db-drill` → `evidence/database-operations.json` |
| Observability | `make observability-proof` → `evidence/observability.json` |
| Security scan | `scripts/scan.py` → `evidence/security-scan.json` |
| Release artifact | `scripts/release.py build` → `evidence/release-<version>.json` |
| Rollback proof | `scripts/release.py rollback` (tested in `tests/test_deployment.py`) |
| Go/no-go | `docs/release-checklist.md`, completed and signed |

## Rollback policy

Rollback is always available and always tested in the same session as the
release:

- the previous artifact is retained in `dist/` and verifiable by checksum;
- `scripts/release.py rollback` preserves the replaced directory;
- the previous container image tag is retained;
- migrations are additive, so the previous service binary is compatible with
  the current schema; a non-additive migration requires an expand/contract pair
  or a snapshot restore (`docs/deployment.md` §6).

## What a release is not

- It is not a claim that every deferred decision is resolved. Open decisions
  (`docs/project-handoff.md`) are listed in the checklist and either closed or
  explicitly accepted as non-blocking for this version.
- It is not a performance claim. Numerical performance SLOs remain deferred
  under D-009 until staging measurements establish them (`docs/staging.md`).
