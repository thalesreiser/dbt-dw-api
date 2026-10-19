# 06 - Traceability matrix

| Requirement | Component | Test | Status |
|---|---|---|---|
| RF-01 | `dbt/models/staging/_sources.yml`, `scripts/direct_load.py`, `src/fundos_api/ingestion.py`, `dbt/macros/source_row_counts.sql` | `tests/test_ingestion*.py`; CI job `sources` (real CVM month: `dbt source freshness`, row count per source, source tests) | ✅ |
| RF-02 | `dbt/models/staging/stg_cvm__*.sql`, `_stg_cvm__models.yml`, `dbt/macros/staging_helpers.sql` | dbt tests in `_stg_cvm__models.yml` (keys, `not_null`, `accepted_values`, `valid_cnpj`, relationships), `dbt/tests/staging/`; CI job `sources`, step `make staging` (`dbt build --select staging` on the real CVM month) | ✅ |
| RF-03 | `dbt/models/marts/`, `dbt/models/intermediate/int_fundo_classe__unificado.sql`, `dbt/seeds/feriados_nacionais.csv` (`scripts/generate_national_holidays.py`); design in `docs/dimensional-model.md` | dims: `unique` + `not_null` on `sk_fundo` and `sk_data`, natural key unique among current versions, `dbt/tests/marts/` (unknown member exactly once, `fl_dia_util` sanity, holidays cover every year); CI job `sources`, step `make marts` (`dbt build --select +marts` on the real CVM month) | 🟡 design and dimensions done (3.2); facts pending (3.3) |
| RF-04 | `dbt/snapshots/snp_cvm__fundo_classe.sql`, `dbt/models/marts/dim_fundo.sql`, `scripts/simulate_scd2_change.py` | `_snapshots.yml` (`dbt_scd_id` unique), `_marts.yml` (natural key + `dt_valido_de` unique, natural key unique among current rows, valid ranges), `dbt/tests/marts/` (one current version per CNPJ, contiguous versions without overlaps); CI job `sources`, steps `make snapshot` and `make scd2-sim` (change one class name on a copy of the warehouse, assert two versions with validity) | ✅ |
| RF-05 | `dbt/tests/`, `*.yml` | staging layer: keys, domains, ranges (`dbt_utils.accepted_range`), date sanity and consistency rules (`dbt_utils.expression_is_true`), raw flag domain (`assert_cadastro_classes_flags_are_known`); CI job `sources`, step `make staging` | 🟡 staging done |
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
| 2026-10-17 | RF-05 (partial): staging tests completed: not_null on every key part and mandatory date, non-negative amounts and counts, report date within its reference month, no date after the load, registry consistency rules, raw flag domain (64 -> 94 data tests) | Task 2.3; RNF-02 | |
| 2026-10-17 | RF-03 design: star schema, grain of `fct_informe_diario` and `fct_captacao_mensal`, `dim_fundo` at class grain with fund-only rows (2026-09: 99.07% of CNPJs match a class, 0.93% a fund only, 0 unmatched), surrogate keys | Task 3.1; R-P3-02; open point of ADR 005 | [002](adr/002-star-schema-vs-wide-table.md) |
| 2026-10-19 | RF-03 dimensions: `int_fundo_classe__unificado` (81,767 CNPJs), `dim_fundo` (81,768 rows incl. the unknown member; single current version until 3.4), `dim_data` (calendar with `fl_dia_util`), seed `feriados_nacionais` generated from the rules in law; CI step `make marts` (94 -> 145 data tests) | Task 3.2 | [002](adr/002-star-schema-vs-wide-table.md), [005](adr/005-cvm-registry-after-resolution-175.md) |
| 2026-10-19 | RF-04: SCD2 snapshot `snp_cvm__fundo_classe` (`check` strategy, hard deletes not invalidated) over `int_fundo_classe__unificado` (now a view); `dim_fundo` rebuilt from it with half-open validity; reproducible change simulation in CI (145 -> 152 data tests) | Task 3.4 | [007](adr/007-registry-snapshot-source-and-hard-deletes.md) |
