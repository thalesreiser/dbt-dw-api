"""RNF-01 load test (task 6.2): p95 of the series queries under local load, with locust.

Traffic mix (weights): 8 series (`GET /v1/fundos/{cnpj}/serie`, default 12-month period),
1 fund list (`GET /v1/fundos`, random page, sometimes filtered), 1 ranking
(`GET /v1/rankings/captacao`). Requests are grouped by endpoint name, so the statistics never
carry a CNPJ.

Environment:
- `LOADTEST_CNPJS_FILE` (required): text file with one 14-digit CNPJ per line, sampled at run
  time from the current versions of `dim_fundo` (`scripts/loadtest_report.py sample`). Real
  CNPJs are never committed.
- `LOADTEST_API_KEY` (optional): sent as `X-API-Key` (task 5.5). Run the API with a high
  `RATE_LIMIT_REQUESTS` (e.g. 1000000), otherwise the test measures 429 responses.

Failures are recorded with the status code only (never the URL, which contains the CNPJ).
Run: `locust -f loadtest/locustfile.py --headless --host http://127.0.0.1:8000 ...`
(see `docs/performance.md`).
"""

import os
import random
from pathlib import Path

from locust import HttpUser, between, task

SERIE = "/v1/fundos/[cnpj]/serie"
FUNDOS = "/v1/fundos"
RANKINGS = "/v1/rankings/captacao"


def _load_cnpjs() -> list[str]:
    path = os.environ.get("LOADTEST_CNPJS_FILE")
    if not path:
        raise RuntimeError("LOADTEST_CNPJS_FILE is not set")
    cnpjs = [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]
    if not cnpjs:
        raise RuntimeError("LOADTEST_CNPJS_FILE has no CNPJ")
    return cnpjs


CNPJS = _load_cnpjs()
API_KEY = os.environ.get("LOADTEST_API_KEY", "")


class ApiUser(HttpUser):  # type: ignore[misc]
    """One client: short think time between requests."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        if API_KEY:
            self.client.headers["X-API-Key"] = API_KEY

    def _get(self, url: str, name: str, params: dict[str, object] | None = None) -> None:
        with self.client.get(url, params=params, name=name, catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(8)
    def serie(self) -> None:
        self._get(f"/v1/fundos/{random.choice(CNPJS)}/serie", SERIE)

    @task(1)
    def fundos(self) -> None:
        params: dict[str, object] = {"limit": 50, "offset": random.randrange(0, 5000, 50)}
        if random.random() < 0.3:
            params["informa_recente"] = "true"
        self._get(FUNDOS, FUNDOS, params)

    @task(1)
    def rankings(self) -> None:
        self._get(RANKINGS, RANKINGS, {"top": 10, "ordem": random.choice(["desc", "asc"])})
