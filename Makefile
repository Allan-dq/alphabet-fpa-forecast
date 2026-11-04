PY ?= python

.PHONY: all install test data refetch clean

## Reproduce every table, chart and number in reports/ from the committed dataset (no network).
all:
	$(PY) run_pipeline.py

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

test:
	$(PY) -m pytest -q

## Rebuild data/processed from the cached XBRL files in data/raw.
data:
	$(PY) run_pipeline.py --rebuild-data

## Download all filings from SEC EDGAR again (needs SEC_USER_AGENT="Name email").
refetch:
	$(PY) run_pipeline.py --fetch

clean:
	rm -f data/fpa.duckdb
