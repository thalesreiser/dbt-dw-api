# 004 - API reading DuckDB directly vs a cache layer

- **Status:** accepted
- **Date:** 2026-10-19

## Context

The warehouse is a single DuckDB file (`data/warehouse.duckdb`, ADR 001) built by dbt in
batch: the marts change only when a new reference month is loaded (`make load` + `make
build`), at most once a day. The API (RF-07 to RF-09) only reads the marts: `dim_fundo`
(~82,000 rows), `fct_informe_diario` (~538,000 rows per month) and `fct_captacao_mensal`
(~25,600 rows per month). RNF-01 targets a p95 below 300 ms on time-series queries, and RNF-03
requires a read-only API with input validation. The API runs on one machine next to the file
(Docker Compose mounts `data/` read-only, bound to `127.0.0.1`).

DuckDB allows many read-only connections to one file, but a writer (dbt) needs the file
unlocked; a plain `duckdb.connect(path)` also creates an empty database when the file is
missing, which would hide a misconfiguration.

## Decision

- The API reads the marts **directly from the DuckDB file, in read-only mode**, with no cache
  layer: `duckdb.connect(path, read_only=True)` (`src/fundos_api/db.py`).
- One connection per request, opened by a FastAPI dependency and always closed when the
  response is done. The file is not held open between requests, so dbt can rebuild the
  warehouse while the API is idle, and each request sees the latest build.
- The API checks that the file exists before connecting and never creates it. A missing or
  unreadable warehouse gives **503** (`/health` and every endpoint), and error bodies never
  include file paths.
- `/health` probes the warehouse with a read-only query and returns the latest reference
  month loaded (`max(dt_mes_competencia)` of `fct_informe_diario`).
- Inputs are validated with Pydantic before any query runs (pagination bounds from the
  settings, CNPJ with 14 digits); values reach SQL as bound parameters only, and the only
  identifier in SQL text (the marts schema) is validated by the settings.
- **LGPD:** the response models expose fund and class data only. No CPF and no name of a
  natural person: the manager columns of `dim_fundo` (`cpf_cnpj_gestor`, `nm_gestor`), which
  may identify an individual, are not exposed, and there is no shareholder data besides the
  aggregate count `nr_cotst`. A test guards the response models.

## Alternatives considered

- **Cache layer (Redis or an in-process LRU) in front of DuckDB.** Would cut latency on hot
  keys, but adds a service or memory to operate, and invalidation on every rebuild. DuckDB
  scans marts of this size in milliseconds, and data changes once a day, so
  the gain does not pay for the complexity. Rejected for now; it is the fallback if RNF-01
  fails.
- **One long-lived connection (or a pool) opened at startup.** Saves the open cost per request
  (a few milliseconds), but keeps the file locked so dbt cannot write while the API runs, and
  the API would serve a stale catalog until a restart. Rejected; to revisit if the load test
  of RNF-01 shows the open cost matters (cursors of one shared connection).
- **Exporting the marts to Parquet or a server database (PostgreSQL) for the API.** Decouples
  readers from the dbt build, but adds an export step and another store for a single-machine
  portfolio project. Rejected.

## Consequences

- Simple and stateless: no cache to invalidate; every response reflects the last dbt build.
- Read-only is enforced by DuckDB itself: any write through the API connection fails, which
  tests prove (`tests/test_db.py`).
- A dbt build that runs while a request is open fails to get the write lock; builds are batch
  jobs and should run with the API idle or stopped.
- The p95 target of RNF-01 must be verified by the RNF-01 load test; if it fails, the
  first step is a shared connection with cursors, then a cache.
- Scaling out means copies of the file on each node; acceptable for this project.
