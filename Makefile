DB ?= ledger.sqlite3

.PHONY: check test run frontend-check frontend-dev \
	db-migrate db-verify db-backup db-retention db-drill observability-proof \
	scan release-check

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check:
	PYTHONPATH=src python3 -m compileall -q src tests
	$(MAKE) test

run:
	PYTHONPATH=src python3 -m ledger

# Frontend checks (require Node.js; run separately from `check`).
frontend-check:
	cd frontend && npm run check

frontend-dev:
	cd frontend && npm run dev

# Database operations (Epic 5). See docs/database-operations.md.
db-migrate:
	PYTHONPATH=src python3 -m ledger.ops migrate --database $(DB)

db-verify:
	PYTHONPATH=src python3 -m ledger.ops integrity --database $(DB)

db-backup:
	PYTHONPATH=src python3 -m ledger.ops backup --database $(DB) --output $(DB).backup-$(shell date -u +%Y%m%dT%H%M%SZ)

db-retention:
	PYTHONPATH=src python3 -m ledger.ops retention

# Epic 6 observability evidence. See docs/observability.md.
observability-proof:
	PYTHONPATH=src python3 observability/run_observability_proof.py

# Epic 5 recovery drill against a freshly seeded representative database.
DRILL_DB ?= /tmp/ledger-ops-drill.sqlite3
DRILL_WORK ?= /tmp/ledger-ops-work
db-drill:
	rm -f $(DRILL_DB)
	rm -rf $(DRILL_WORK)
	PYTHONPATH=src python3 product_proof/seed_database.py $(DRILL_DB)
	PYTHONPATH=src python3 -m ledger.ops drill --database $(DRILL_DB) \
		--workdir $(DRILL_WORK) --evidence evidence/database-operations.json

# Epic 7 security scanning gate. See docs/deployment.md.
scan:
	python3 scripts/scan.py --require-tools

# Epic 7 release artifact build + verification. See docs/release.md.
release-check:
	python3 scripts/release.py build --version "$$(cat VERSION)" --output dist
	python3 scripts/release.py verify --artifact "dist/ledger-$$(cat VERSION).tar.gz"
