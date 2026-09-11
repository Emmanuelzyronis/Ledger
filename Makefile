DB ?= ledger.sqlite3

.PHONY: check test run frontend-check frontend-dev \
	db-migrate db-verify db-backup db-retention

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
