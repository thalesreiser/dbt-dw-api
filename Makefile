DBT_ARGS = --project-dir dbt --profiles-dir dbt
PYTHON ?= python
# Same DuckDB file for the loader and dbt (paths relative to the repository root).
DUCKDB_PATH ?= data/warehouse.duckdb
export DUCKDB_PATH
# Reference month to load (YYYY-MM); empty = previous month. COMPETENCIAS = months to load.
COMPETENCIA ?=
COMPETENCIAS ?= 1
LOAD_ARGS = --competencias $(COMPETENCIAS) $(if $(COMPETENCIA),--competencia $(COMPETENCIA),)

.PHONY: install up down deps load load-p1 freshness row-counts sources staging snapshot scd2-sim negative-tests negative-fixture marts build docs docs-coverage docs-serve api lint fmt test test-integration

install:
	pip install -e ".[dev,dbt]" && pre-commit install

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

deps:
	dbt deps $(DBT_ARGS)

load:  ## RF-01 / R-P3-01: direct load of the CVM open data into DuckDB
	$(PYTHON) scripts/direct_load.py $(LOAD_ARGS)

load-p1:  ## RF-01: load the P1 Parquet (P1_PATH=<base directory>)
	$(PYTHON) scripts/direct_load.py --source p1-parquet --path $(P1_PATH) $(if $(COMPETENCIA),$(LOAD_ARGS),)

freshness:  ## RF-01: freshness of the raw sources
	dbt source freshness $(DBT_ARGS)

row-counts:  ## RF-01: row count per source (fails if a source is empty)
	dbt run-operation source_row_counts $(DBT_ARGS)

sources: deps freshness row-counts  ## RF-01: freshness + row counts + source tests
	dbt test --select "source:*" $(DBT_ARGS)

staging: deps  ## RF-02: build the stg_ models and run their tests (and the source tests)
	dbt build --select staging --indirect-selection cautious $(DBT_ARGS)

snapshot: deps  ## RF-04: SCD2 snapshot of the unified registry (with the models upstream)
	dbt build --select +snp_cvm__fundo_classe $(DBT_ARGS)

scd2-sim:  ## RF-04: simulate a registry change on a copy of the warehouse; prove 2 versions
	$(PYTHON) scripts/simulate_scd2_change.py

negative-tests:  ## RF-05: inject rows breaking RN-01/RN-02 into a copy of the warehouse; assert the tests fail
	$(PYTHON) scripts/negative_tests.py

negative-fixture: deps  ## RF-05 (4.3): network-free negative suite on synthetic seeds; each case fails exactly its expected tests
	$(PYTHON) scripts/negative_fixture_tests.py

marts: deps  ## RF-03: build the seeds and the marts with everything upstream, and run their tests
	dbt build --select +marts $(DBT_ARGS)

build: deps  ## RNF-02: fails if any test fails
	dbt build $(DBT_ARGS)

docs: deps  ## RF-06: dbt docs (manifest + catalog; needs the built warehouse for the catalog)
	dbt docs generate $(DBT_ARGS)

docs-coverage:  ## RF-06: fail if a model, snapshot, seed or exposure, or a column, lacks a description
	$(PYTHON) scripts/check_docs_coverage.py --target dbt/target

docs-serve:  ## RF-06: open the generated docs on localhost:8080
	dbt docs serve --port 8080 $(DBT_ARGS)

api:  ## RNF-03: read-only API on localhost:8000 (reads DUCKDB_PATH)
	uvicorn fundos_api.main:app --reload --host 127.0.0.1 --port 8000

lint:
	ruff check src tests scripts && black --check src tests scripts && mypy src scripts

fmt:
	ruff check --fix src tests scripts && black src tests scripts

test:  ## unit tests (the integration tests are excluded)
	pytest

test-integration: deps  ## 5.6: API integration tests over a test warehouse built by dbt from synthetic raw data
	pytest -m integration
