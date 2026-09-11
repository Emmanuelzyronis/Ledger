.PHONY: check test run

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check:
	PYTHONPATH=src python3 -m compileall -q src tests
	$(MAKE) test

run:
	PYTHONPATH=src python3 -m ledger
