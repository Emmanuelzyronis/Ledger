.PHONY: check test run frontend-check frontend-dev

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
