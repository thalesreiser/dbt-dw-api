DBT_ARGS = --project-dir dbt --profiles-dir dbt
PYTHON ?= python
# Same DuckDB file for the loader and dbt (paths relative to the repository root).
DUCKDB_PATH ?= data/warehouse.duckdb
export DUCKDB_PATH
# Reference month to load (YYYY-MM); empty = previous month. COMPETENCIAS = months to load.
COMPETENCIA ?=
COMPETENCIAS ?= 1
LOAD_ARGS = --competencias $(COMPETENCIAS) $(if $(COMPETENCIA),--competencia $(COMPETENCIA),)

.PHONY: install up down deps load load-p1 freshness row-counts sources staging snapshot scd2-sim marts build docs api lint fmt test

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
	dbt build --select staging $(DBT_ARGS)

snapshot: deps  ## RF-04: SCD2 snapshot of the unified registry (with the models upstream)
	dbt build --select +snp_cvm__fundo_classe $(DBT_ARGS)

scd2-sim:  ## RF-04: simulate a registry change on a copy of the warehouse; prove 2 versions
	$(PYTHON) scripts/simulate_scd2_change.py

marts: deps  ## RF-03: build the seeds and the marts with everything upstream, and run their tests
	dbt build --select +marts $(DBT_ARGS)

build: deps  ## RNF-02: fails if any test fails
	dbt build $(DBT_ARGS)

docs:  ## RF-06
	dbt docs generate $(DBT_ARGS)

api:
	uvicorn fundos_api.main:app --reload

lint:
	ruff check src tests scripts && black --check src tests scripts && mypy src scripts

fmt:
	ruff check --fix src tests scripts && black src tests scripts

test:
	pytest
