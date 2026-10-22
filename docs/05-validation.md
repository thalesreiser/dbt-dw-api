# 05 - Validation

How each requirement of [02](02-analysis-and-prioritization.md) was validated. CI runs are in
[Actions](https://github.com/thalesreiser/dbt-dw-api/actions/workflows/ci.yml); the jobs are
described in the README ("Continuous integration"). Run ids below are the evidence runs; every
pull request reruns the same jobs.

## Requirements review checklist
- [x] Each requirement is singular, verifiable, unambiguous and traceable (one row per ID in [06](06-traceability.md))
- [x] Every "Must" RF has an executable acceptance criterion (Gherkin in [03](03-specification.md), automated in CI)
- [x] Numeric targets (RNF) were measured and recorded (RNF-01 in [performance.md](performance.md))

## Acceptance criteria execution results

| ID | Criterion | Result | Evidence | Date |
|---|---|---|---|---|
| RF-01 | Source tables available as dbt `sources` | ✅ freshness and row count per source pass on real CVM months | CI job `sources` (`make load COMPETENCIAS=2`, `make freshness`, `make row-counts`, source tests), run [39833377949](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39833377949) | 2026-10-22 |
| RF-02 | Every source has a `stg_` model with standardized columns | ✅ 3 staging views, their tests pass | `sources`, step `make staging` | 2026-10-22 |
| RF-03 | Facts reference dimensions with no orphans | ✅ `relationships` tests on every FK pass; incremental re-run keeps the row count | `sources`, steps `make marts` and `Incremental fact is idempotent` | 2026-10-22 |
| RF-04 | A registry change keeps both versions with validity dates | ✅ two contiguous versions after a simulated name change | `sources`, steps `make snapshot` and `make scd2-sim` | 2026-10-22 |
| RF-05 | A test fails when invalid data is inserted on purpose | ✅ 11/11 rule tests fail on a tampered copy; 9 synthetic cases fail exactly their expected tests, the clean case passes | `sources` (`make negative-tests`), `negative-fixture`; table in [testing.md](testing.md) | 2026-10-22 |
| RF-06 | `dbt docs generate` shows description and lineage of every mart | ✅ coverage check passes (no undocumented item); lineage reviewed; site published | `sources` (`make docs docs-coverage`, artifact `dbt-docs`), workflow `docs.yml`, https://thalesreiser.github.io/dbt-dw-api/ | 2026-10-22 |
| RF-07 | Status filter returns only matching funds, paginated | ✅ | `lint-test` (`tests/test_fundos.py`), `api-integration` (integration tests); real data: `compose` (`situacao=em funcionamento normal&limit=2`: 2 items, total 33,815) | 2026-10-22 |
| RF-08 | Ordered series, or 404 for an unknown CNPJ | ✅ | `lint-test` (`tests/test_serie.py`), `api-integration`; real data: `compose` (series of the ranking leader, 404 for an absent CNPJ) | 2026-10-22 |
| RF-09 | Top N of the month | ✅ | `lint-test` (`tests/test_rankings.py`), `api-integration`; real data: `compose` (`top=3`) | 2026-10-22 |
| RF-10 | Without a key 401; above the limit 429 | ✅ | `lint-test` (`tests/test_security.py`: 401, 429 with `Retry-After`, 503 fail-closed); `compose` (401 missing and wrong key) | 2026-10-22 |
| RF-11 | No endpoint violates the OpenAPI contract | ✅ 0 violations | `api-integration`, step `make test-contract` (Schemathesis, positive and negative generation) | 2026-10-22 |
| RNF-01 | p95 below 300 ms on time-series queries | ✅ p95 54 ms (CI, 2 months, 20 users, 0% errors); 232 ms on a laptop | manual workflow `loadtest.yml`, run [39487103055](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39487103055); [performance.md](performance.md) | 2026-10-20 |
| RNF-02 | `dbt build` fails CI if any test fails | ✅ a deliberately failing test turned the jobs red, then was removed | PR #42, runs [39781439210](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39781439210) and [39782069016](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39782069016) | 2026-10-22 |
| RNF-03 | Read-only API; key out of the repository; input validation | ✅ writes rejected, missing file never created, 422 before any query, no personal data in schemas, key only in `.env` (git- and docker-ignored) | `lint-test` (`tests/test_db.py`, `test_params.py`, `test_schemas_config.py`, `test_security.py`); `compose` (read-only volume, port on `127.0.0.1`) | 2026-10-22 |
| RNF-04 | Runs via Docker Compose | ✅ `make up` built the image, loaded 2026-09, `dbt build` 216/216 pass, API healthy in ~1 min; README examples 200 and 401 without a key. Optional Athena adapter not built (ADR 001) | CI job `compose`, run [39833377949](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39833377949) (PR #44) | 2026-10-22 |
| RNF-05 | Layers staging -> intermediate -> marts with a documented convention | ✅ review: every model follows [naming-conventions.md](naming-conventions.md); schemas per layer | review; `dbt parse` in `lint-test` | 2026-10-22 |
| RN-01 | Net inflows = inflows - redemptions | ✅ `net_inflow` tests at the daily and monthly grain, reconciliation with staging; negative proof | `sources`, `negative-fixture` | 2026-10-22 |
| RN-02 | BRL decimals; dates in UTC-3 only at presentation | ✅ `columns_data_type` and date tests; negative proof | `sources`, `negative-fixture` | 2026-10-22 |
| RST-01 | No recurring cost | ✅ local DuckDB, GitHub-hosted CI and Pages, public data | ADR 001 | 2026-10-22 |
