# Testing the tests: negative suites (RF-05)

A test that never fails proves nothing. Two suites insert invalid data on purpose and assert
that the dbt tests catch it.

| Suite | Data | Needs network | Command | CI |
|---|---|---|---|---|
| Negative proof on the real warehouse (task 4.1) | copy of the built warehouse (real CVM months), rows tampered with SQL | yes (CVM load) | `make negative-tests` | job `sources` |
| Negative fixture suite (task 4.3) | synthetic seeds `dbt/seeds/negative/*.csv` | no (only `dbt deps`) | `make negative-fixture` | job `negative-fixture` |

## Negative fixture suite (task 4.3)

**Given** invalid data inserted on purpose, **when** `dbt test` runs, **then** at least one test
fails, and in fact exactly the tests expected for that kind of error, with the expected number
of failing rows.

How it works (`scripts/negative_fixture_tests.py`):

1. The seeds in `dbt/seeds/negative/` are synthetic copies of the three raw sources (CVM column
   names; every CNPJ synthetic, with valid check digits; no natural persons). A column
   `negative_case` tags each row: empty = clean row, otherwise the row exists only for that
   case. The seeds are disabled unless `--vars '{negative_fixture: true}'` is passed
   (`dbt_project.yml`), so `dbt seed` / `dbt build` in production never load them.
2. `dbt seed --vars '{negative_fixture: true}'` loads them once into a template DuckDB file in a
   temporary directory (the real warehouse is never touched).
3. For every case, on a fresh copy of the template: the clean rows plus the case rows become the
   `raw` tables the sources read (all VARCHAR, like the loader); `dbt build` without tests builds
   every model and the snapshot; the cases that cannot come from raw data (RN-01, an orphan fact
   key, an SCD2 overlap: the models compute them correctly) tamper the built tables with SQL and
   rebuild what depends on them; then `dbt test --store-failures` runs **all** tests.
4. The script compares the failing tests and their failing row counts (`failures` in
   `run_results.json`) with the expected map below: a missing failure, an extra failure or a
   different row count fails the suite. Warnings (`severity: warn`) are not failures.

Fixture: one fund adapted to Resolution 175 with one class (`11.222.333/0001-81`), one fund
without classes (`11.555.666/0001-22`), five daily reports in 2026-08 and 2026-09.

## Results

202 data tests in the project. Run of 2026-10-20 (same result in CI):

| Case | Invalid data | Failing tests (failing rows) |
|---|---|---|
| `clean` | none | none: 202 pass |
| `null_key` | daily report row without CNPJ | `source_not_null_cvm_informe_diario_CNPJ_FUNDO_CLASSE` (1), `not_null_stg_cvm__informe_diario_cnpj_fundo_classe` (1), `not_null_fct_informe_diario_cnpj_fundo_classe` (1), `not_null_fct_captacao_mensal_cnpj_fundo_classe` (1), `assert_rn01_monthly_net_inflow_matches_staging` (2), `assert_fct_captacao_mensal_reconciles_daily` (2) |
| `duplicate_key` | daily report row repeated (same class and date) | `unique_combination_of_columns` on the source (1), on `stg_cvm__informe_diario` (1) and on `fct_informe_diario` (1) |
| `orphan_fk` | class whose fund registry id does not exist | `relationships` class -> fund on the source (1) and on `stg_cvm__cadastro_classes` (1) |
| `orphan_fact_fk` | daily fact row pointing to no `dim_fundo` version (SQL) | `relationships_fct_informe_diario_sk_fundo__sk_fundo__ref_dim_fundo_` (1) |
| `rn01_net_inflow` | net inflow != inflows - redemptions on one daily and one monthly fact row (SQL) | `rn01_fct_informe_diario_net_inflow` (1), `rn01_fct_captacao_mensal_net_inflow` (1), `expression_is_true` on `vl_captc_liquida_mes` (1), `assert_rn01_monthly_net_inflow_matches_staging` (1), `assert_fct_captacao_mensal_reconciles_daily` (2) |
| `rn02_negative_flow` | negative daily inflow | `accepted_range` on `stg_cvm__informe_diario.vl_captc_dia` (1), `rn02_stg_informe_diario_flows_not_negative` (1), `rn02_fct_informe_diario_flows_not_negative` (1), `rn02_fct_captacao_mensal_flows_not_negative` (1) |
| `rn02_future_date` | report dated 2999-12-15 (in its own reference month) | `rn02_stg_informe_diario_no_future_date` (1), `rn02_fct_informe_diario_no_future_date` (1), `rn02_fct_captacao_mensal_no_future_date` (1), report date after the load date in staging (1); the calendar ends with the current year, so `relationships` to `dim_data` from both facts (1 each) |
| `rn02_outside_month` | report date 2026-08-28 in the 2026-09 file | `rn02_stg_informe_diario_date_in_reference_month` (1), `expression_is_true` date in month on staging (1) and on `fct_informe_diario` (1) |
| `scd2_two_current` | a second open version of the same CNPJ in the snapshot (SQL) | `assert_dim_fundo_one_current_version` (1), `assert_dim_fundo_versions_contiguous` (2), `unique_dim_fundo_cnpj_fundo_classe` among current versions (1) |

Reading the results: every injected error is caught at the first layer it reaches (source,
then staging) and again in every layer it propagates to, and the clean data passes every test,
so the failures come from the injected rows and not from the fixture.

Run one case: `python scripts/negative_fixture_tests.py --case rn02_future_date`. The failing
rows of each test are stored by `--store-failures` in the temporary warehouse (schema
`dbt_test__audit`), discarded at the end of the run.

## API integration tests

**Given** a warehouse built by the actual dbt models, **when** each endpoint is called over
HTTP, **then** the responses have the documented shape and their numbers match the marts.

Unit tests (`tests/test_*.py`, `make test`) run against a hand-built DuckDB with the marts'
columns. The integration layer (`tests/integration/test_api_integration.py`, marker
`integration`) closes the gap between that DDL and the real SQL:

1. **Test warehouse.** `scripts/build_test_warehouse.py` loads the CSV files in
   `tests/fixtures/warehouse/` (synthetic rows in the layout of the three CVM sources; every
   CNPJ synthetic with valid check digits; no natural persons) into the `raw` tables, every
   column as VARCHAR like the loader, in a new DuckDB file, then runs `dbt build` of the real
   project on it (seeds, staging, snapshot, marts and all 206 data tests; it fails if any
   fails). The real warehouse is never touched. A session-scoped fixture builds it once in a
   temporary directory (~1 min, mostly dbt parsing).
2. **Requests.** An `httpx.AsyncClient` with the ASGI transport calls the app created with
   `create_app` (no server, no network); settings come from the environment (`DUCKDB_PATH`,
   `API_KEY`), and every request sends the header `X-API-Key` with the module constant
   `TEST_API_KEY`.
3. **Cross-checks.** Direct read-only DuckDB queries on the same warehouse give the expected
   values (current `dim_fundo` rows, `fl_informa_recente`, `fct_informe_diario` points,
   `fct_captacao_mensal` ranking), and the daily series of a class adds up to its monthly net
   inflows (RN-01).

Fixture (current `dim_fundo` rows; latest month 2026-09):

| CNPJ | Kind | Status | Reports | Net inflows 2026-08 / 2026-09 |
|---|---|---|---|---|
| `11222333000181` | class A1 of fund A (FIF) | normal | 2026-08, 2026-09 | 40.00 / 30.00 |
| `11222333000262` | class A2 of fund A, two subclasses | normal | 2026-08, 2026-09 | 20.00 / 154.50 |
| `11444777000242` | fund C (FI, no classes) | `CANCELADO` | 2026-08 only | -200.00 / - |
| `11555666000122` | fund B (FI, no classes) | normal | 2026-09 | - / -30.00 |

Cases (34 tests):

| Endpoint | Cases |
|---|---|
| `GET /health` | 200 with the latest month of the daily fact |
| `GET /v1/fundos` | current versions only, unknown member excluded, fund vs class rows; filters `situacao`, `informa_recente` (alone and with `situacao=CANCELADO`), `tp_fundo`, `tp_classe`, `nome`, combined; `limit`/`offset` pages, total and offset past the end; 422 on invalid filters and pagination |
| `GET /v1/fundos/{cnpj}/serie` | default period (latest day of the CNPJ, 12 months back), explicit period, subclass roll-up (`vl_quota` null on multi-subclass days), `por_subclasse=true` against the fact rows, JSON numbers, empty list for a known CNPJ without points, 404 for an unknown CNPJ, 422 on `inicio > fim`, a range above 1,830 days and a malformed CNPJ |
| `GET /v1/rankings/captacao` | default month against the monthly fact, full item fields, `ordem=asc`, explicit `mes` with `top`, a cancelled fund in the month it reported, 404 for a month without data, 422 on `top`, `ordem` and `mes` |

Run: `make test-integration` (runs `dbt deps` first) or `pytest -m integration`. Plain `pytest`
deselects them (`-m "not integration"` in `pyproject.toml`); CI runs them in the job
`api-integration`.
