DBT = dbt --project-dir dbt --profiles-dir dbt

.PHONY: install up down deps build docs api lint fmt test

install:
	pip install -e ".[dev,dbt]" && pre-commit install

up:
	docker compose -f infra/docker-compose.yml up -d --build

down:
	docker compose -f infra/docker-compose.yml down

deps:
	$(DBT) deps

build: deps  ## RNF-02: falha se qualquer teste falhar
	$(DBT) build

docs:  ## RF-06
	$(DBT) docs generate

api:
	uvicorn fundos_api.main:app --reload

lint:
	ruff check src tests && black --check src tests && mypy src

fmt:
	ruff check --fix src tests && black src tests

test:
	pytest
