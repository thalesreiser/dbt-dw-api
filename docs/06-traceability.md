# 06 - Traceability matrix

| Requirement | Component | Test | Status |
|---|---|---|---|
| RF-01 | `dbt/models/staging/_sources.yml`, `scripts/direct_load.py`, `src/fundos_api/ingestion.py`, `dbt/macros/source_row_counts.sql` | `tests/test_ingestion*.py`; CI job `sources` (real CVM month: `dbt source freshness`, row count per source, source tests) | ✅ |
| RF-02 | `dbt/models/staging/stg_cvm__*.sql`, `_stg_cvm__models.yml`, `dbt/macros/staging_helpers.sql` | dbt tests in `_stg_cvm__models.yml` (keys, `not_null`, `accepted_values`, `valid_cnpj`, relationships), `dbt/tests/staging/`; CI job `sources`, step `make staging` (`dbt build --select staging` on the real CVM month) | ✅ |
| RF-03 | `dbt/models/marts/` | | ⬜ |
| RF-04 | `dbt/snapshots/` | | ⬜ |
| RF-05 | `dbt/tests/`, `*.yml` | | ⬜ |
| RF-06 | `dbt docs` | | ⬜ |
| RF-07 | `fundos_api` | | ⬜ |
| RF-08 | `fundos_api` | | ⬜ |
| RF-09 | `fundos_api` | | ⬜ |
| RF-10 | `fundos_api` | | ⬜ |
| RF-11 | CI (Schemathesis) | | ⬜ |
| RNF-01 | load test (locust/hey) | | ⬜ |
| RNF-05 | `dbt/dbt_project.yml` (layers), `docs/naming-conventions.md`, `dbt/macros/generate_schema_name.sql` | review; staging models and tests follow the convention | 🟡 staging done |

## Change log
| Date | Change | Reason | ADR |
|---|---|---|---|
| 2026-10-16 | RF-01: sources `informe_diario`, `cadastro_fundos`, `cadastro_classes` with freshness; direct CVM loader with pluggable P1 Parquet source | Task 2.1; R-P3-01 (P1 not ready); Resolution 175 registry | [005](adr/005-cvm-registry-after-resolution-175.md) |
| 2026-10-17 | RF-02: staging models `stg_cvm__informe_diario`, `stg_cvm__cadastro_fundos`, `stg_cvm__cadastro_classes` with tests; RNF-05 naming convention documented | Task 2.2; registry keys repeat in the source | [006](adr/006-staging-grain-and-deduplication.md) |
