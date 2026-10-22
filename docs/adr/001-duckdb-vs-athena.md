# 001 - DuckDB vs Athena as the warehouse

- **Status:** accepted
- **Date:** 2026-10-22 (records the choice made at the start of the project, 2026-10-16)

## Context

The project models the CVM investment fund data (RF-01 to RF-06) and serves it through a
read-only API (RF-07 to RF-11). The volume is small for an analytical engine: about 538,000
daily report rows per reference month, ~82,000 registry rows and a few hundred calendar rows.
Constraint RST-01 forbids recurring cost, RNF-04 asks for an environment that runs anywhere with
Docker Compose, and RNF-01 asks for a p95 below 300 ms on the time-series queries. The sibling
project P1 (`aws-fundos-pipeline`) publishes Parquet on S3, which Athena could query in place.

## Decision

- The warehouse is **DuckDB**, one local file (`data/warehouse.duckdb`, or the `warehouse`
  volume under Docker Compose), built by **dbt-duckdb** (profile `fundos_dw`, `dbt/profiles.yml`).
- The source is loaded into the `raw` schema of that file by `scripts/direct_load.py` (CVM open
  data, or the P1 Parquet with `--source p1-parquet`), so dbt and the API never depend on a cloud
  service.
- The models use dbt and standard SQL only (the DuckDB-specific bits are confined to the loader
  and a few macros), so a second dbt target, e.g. `dbt-athena` over the P1 bucket, can be added
  later. That target is **not** built or tested here.

## Alternatives considered

- **Amazon Athena (dbt-athena) over the P1 Parquet.** Serverless and close to P1, but every query
  is billed by data scanned, needs an AWS account and credentials in CI, and has a latency of
  seconds per query: it breaks RST-01 and makes the RNF-01 target unrealistic for an API that
  queries per request. Rejected as the main warehouse; kept as a possible extra target.
- **PostgreSQL in a container.** Free and well known, but row-oriented, another service to run
  and load, and slower on the monthly aggregations. Rejected.
- **BigQuery / Snowflake free tiers.** Need accounts and credentials and have quotas; not
  reproducible offline. Rejected.

## Consequences

- Zero cost and fully reproducible: CI downloads real CVM months, builds the warehouse in about
  two minutes and throws it away; `make up` does the same in Docker.
- Fast: the API reads the marts directly (ADR 004) and the series p95 is 54 ms on CI
  (`docs/performance.md`).
- Single writer, single file: dbt needs the file unlocked, so builds run with the API idle
  (Compose runs the build before starting the API); there is no concurrent multi-user write or
  horizontal scaling (README, "Limitations").
- The "optional Athena" part of RNF-04 stays a documented extension point, not an implemented
  adapter (`docs/06-traceability.md`).
