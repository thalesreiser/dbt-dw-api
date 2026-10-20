# Performance (RNF-01)

Target: **p95 below 300 ms on the time-series queries** (`GET /v1/fundos/{cnpj}/serie`),
measured with a local load test (task 6.2). ADR 004 (API reading DuckDB directly, one
read-only connection per request) depends on it.

## Method

- **Tool:** [locust](https://locust.io) `2.37.14`, headless, pinned in the optional extra
  `loadtest` (`pip install -e ".[loadtest]"`); installed only by the load test workflow.
- **Script:** `loadtest/locustfile.py`. Each simulated user waits 0.1-0.5 s between requests
  and picks, by weight:
  - 8: `GET /v1/fundos/{cnpj}/serie` with the default period (the last 12 months of the CNPJ);
  - 1: `GET /v1/fundos?limit=50&offset=<random page>` (30% with `informa_recente=true`);
  - 1: `GET /v1/rankings/captacao?top=10` (`ordem` desc or asc, default month).
- **CNPJs:** 500 sampled at run time from the current versions of `dim_fundo` that report in
  the latest month (`scripts/loadtest_report.py sample`). The file stays in the runner's temp
  directory; no real CNPJ is committed or uploaded.
- **Statistics:** requests are grouped by endpoint name (`/v1/fundos/[cnpj]/serie`), and
  failures are recorded with the status code only, so the statistics never carry a CNPJ.
  `scripts/loadtest_report.py report` turns the locust CSV into per-endpoint requests, RPS,
  error rate and p50/p95/p99 (JSON and Markdown; aggregates only). Locust rounds percentiles
  above 100 ms to 2 significant digits.
- **Server:** production-like `uvicorn fundos_api.main:app` with no `--reload`, a fixed number of
  worker processes (default 2) and no access log, on the same machine as the load generator.
- **Authentication (task 5.5):** the script sends `X-API-Key` from `LOADTEST_API_KEY`. Run the
  API with that key in `API_KEY` and a rate limit high enough not to measure 429 responses
  (`RATE_LIMIT_REQUESTS=1000000`); the workflow does both. Before 5.5 the header is ignored.

## Environment

- **CI (reference):** workflow `.github/workflows/loadtest.yml`, manual (`workflow_dispatch`),
  on a GitHub-hosted `ubuntu-latest` runner. It builds the warehouse exactly like the CI job
  `sources` (`make load COMPETENCIAS=2` from CVM, then `make marts`), starts the API, warms it
  up with 20 requests and runs locust for 3 minutes with 20 users. Inputs: months to load,
  users, duration, workers. The report goes to the job summary and the artifact
  `loadtest-report` (`loadtest.json`, `loadtest.md`).
- **Local (preliminary):** Windows 11 laptop, 8 logical CPUs, 7.7 GB RAM, shared with other
  workloads during the run; warehouse built with `dbt build --select +marts` on one CVM month
  (2026-09: `fct_informe_diario` 538,099 rows, `dim_fundo` 81,768 rows, so a default series has
  up to ~21 points). Locust is not installed in the local environment, so the local run used a
  small thread-based driver with the same mix, think time and endpoint grouping (10 users,
  90 s, uvicorn with 2 workers); its percentiles are exact, not bucketed.

## Results

| Run | Data | Endpoint | Requests | RPS | Errors | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Local laptop, 2026-10-20 | 1 month | `/v1/fundos/[cnpj]/serie` | 1,625 | 18.0 | 0% | 112 | **232** | 327 |
| Local laptop, 2026-10-20 | 1 month | `/v1/fundos` | 195 | 2.2 | 0% | 136 | 228 | 302 |
| Local laptop, 2026-10-20 | 1 month | `/v1/rankings/captacao` | 189 | 2.1 | 0% | 215 | 355 | 458 |
| [CI run 39487103055](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39487103055), 2026-10-20 | 2 months | `/v1/fundos/[cnpj]/serie` | 8,261 | 46.1 | 0% | 31 | **54** | 69 |
| [CI run 39487103055](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39487103055), 2026-10-20 | 2 months | `/v1/fundos` | 1,090 | 6.1 | 0% | 48 | 77 | 93 |
| [CI run 39487103055](https://github.com/thalesreiser/dbt-dw-api/actions/runs/39487103055), 2026-10-20 | 2 months | `/v1/rankings/captacao` | 1,097 | 6.1 | 0% | 82 | 120 | 140 |

**Reference run (CI, 4 vCPU GitHub runner, 2 CVM months, uvicorn 2 workers, locust 20 users for 3 min, API key on and rate limit raised for the run): the series p95 is 54 ms, well below the 300 ms target, with 0% errors** (10,448 requests, 58 RPS in total). The connection-per-request cost measured locally still dominates; the shared-connection fallback of ADR 004 stays unnecessary.

Locally the target is **met** (p95 232 ms < 300 ms), with no errors. The CI row is the
reference result and is filled in after the first manual run.

### Where the time goes

Profiling one request locally (single client, warm cache):

| Step | Time (ms) |
|---|---:|
| Open + close a read-only DuckDB connection (ADR 004: one per request) | ~64 |
| CNPJ lookup in `dim_fundo` | ~7 |
| Latest reported day of the CNPJ (`max(sk_data)`) | ~5 |
| Series query (12-month window, grouped by day) | ~8 |

The connection open is about 70-75% of the server time and does not depend on the data
volume. On a synthetic 12-month fact (the real month shifted back 11 times, 6.46 million rows)
the two fact queries took ~17 and ~28 ms; sorting the fact by `cnpj_fundo_classe, sk_data`
within each month cut them to ~12 and ~18 ms (the CVM files already arrive grouped by CNPJ, so
DuckDB's min/max zone maps prune most row groups without an explicit sort).

### Optimization (not applied)

The target is met, so ADR 004 stays as decided (one connection per request, the file is not
held open, and dbt can rebuild while the API is idle). Its documented fallback was measured
locally as an experiment (one read-only connection per worker, a cursor per request), same
run settings:

| Variant | Series p50 (ms) | Series p95 (ms) | Series p99 (ms) | RPS (all) |
|---|---:|---:|---:|---:|
| Connection per request (current) | 112 | 232 | 327 | 22.2 |
| Shared connection, cursor per request (experiment) | 50 | 132 | 260 | 26.0 |

If the CI reference run misses the target, the first step is that fallback (about -100 ms on
the series p95 locally), at the cost of keeping the file locked while the API runs; then a
sorted fact; a cache layer only after both.

## How to rerun

CI (reference): Actions, workflow **Load test**, *Run workflow* (inputs optional).

Locally, on a built warehouse (`make load` + `make build`):

```bash
pip install -e ".[loadtest]"
python scripts/loadtest_report.py sample -n 500 --out /tmp/cnpjs.txt
API_KEY=local RATE_LIMIT_REQUESTS=1000000 \
  uvicorn fundos_api.main:app --host 127.0.0.1 --port 8000 --workers 2 --no-access-log &
LOADTEST_CNPJS_FILE=/tmp/cnpjs.txt LOADTEST_API_KEY=local \
  locust -f loadtest/locustfile.py --headless --host http://127.0.0.1:8000 \
  -u 20 -r 5 -t 3m --only-summary --csv /tmp/locust --exit-code-on-error 0
python scripts/loadtest_report.py report --stats /tmp/locust_stats.csv \
  --json loadtest.json --markdown loadtest.md --context "my machine"
```

`report --fail-on-miss` exits 1 when the series p95 is not below 300 ms.
