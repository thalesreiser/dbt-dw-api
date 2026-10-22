"""OpenAPI contract tests (task 6.1, RF-11): Schemathesis against every operation of the API.

Schemathesis reads the app's own `/openapi.json` and generates requests from it, both valid
(positive) and schema-violating (negative: wrong types, out-of-range numbers, bad patterns),
then runs every default check on each response:

- `not_a_server_error`: no 5xx;
- `status_code_conformance`: the status code is documented for the operation;
- `content_type_conformance`: the `Content-Type` is the documented one;
- `response_schema_conformance`: the body validates against the documented schema;
- `response_headers_conformance`: documented headers (e.g. `Retry-After`) match their schema;
- `negative_data_rejection` / `positive_data_acceptance`: invalid input gives 4xx, valid input
  is not rejected with 4xx (404 for an unknown CNPJ / a month without data is allowed);
- `ignored_auth`: the `X-API-Key` security scheme is enforced (401 without a valid key);
- plus `missing_required_header`, `unsupported_method`, `use_after_free`, ...

The app runs in-process over the test warehouse built by `scripts/build_test_warehouse.py`
(the same synthetic data and dbt build as the integration tests), with the test key and a rate
limit high enough that 429 never interferes. Generation is deterministic and bounded
(`MAX_EXAMPLES` per operation and mode), so the suite is reproducible and fast.

Run with `make test-contract` (or `pytest -m contract`); excluded from plain `pytest`. Set
`TEST_WAREHOUSE_PATH` to reuse an already built test warehouse instead of building one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import schemathesis
from fastapi import FastAPI
from hypothesis import HealthCheck, settings
from pydantic import SecretStr
from schemathesis import GenerationMode
from schemathesis.checks import CheckFunction, not_a_server_error, positive_data_acceptance

from fundos_api.config import Settings
from fundos_api.main import create_app
from fundos_api.routers.serie import MAX_PERIODO_DIAS

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_API_KEY = "contract-test-key"
MAX_EXAMPLES = 60


@pytest.fixture(scope="session")
def contract_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    prebuilt = os.environ.get("TEST_WAREHOUSE_PATH")
    if prebuilt:
        return Path(prebuilt)
    path = tmp_path_factory.mktemp("contract_warehouse") / "warehouse.duckdb"
    proc = subprocess.run(
        [sys.executable, "scripts/build_test_warehouse.py", "--output", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"test warehouse build failed:\n{proc.stdout}\n{proc.stderr}"
    return path


@pytest.fixture(scope="session")
def contract_app(contract_warehouse: Path) -> FastAPI:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        duckdb_path=contract_warehouse,
        api_key=SecretStr(CONTRACT_API_KEY),
        rate_limit_requests=1_000_000,
    )
    return create_app(settings)


@pytest.fixture(scope="session")
def api_schema(contract_app: FastAPI) -> schemathesis.BaseSchema:
    loaded = schemathesis.openapi.from_asgi("/openapi.json", contract_app)
    loaded.config.generation.update(
        modes=[GenerationMode.POSITIVE, GenerationMode.NEGATIVE],
        max_examples=MAX_EXAMPLES,
        deterministic=True,
        # Documented exclusions: unknown query parameters are ignored by design (`params.py`),
        # and the API key is always sent (`ignored_auth` still checks that it is enforced).
        allow_extra_parameters=False,
        with_security_parameters=False,
    )
    return loaded


schema = schemathesis.pytest.from_fixture("api_schema")


# Messages of the `/serie` period rule (`fundos_api.routers.serie._check_period`).
PERIOD_RULE_MESSAGES = (
    "inicio must not be after fim",
    f"period must not exceed {MAX_PERIODO_DIAS} days",
)


def rejected_by_period_rule(case: schemathesis.Case[Any], response: schemathesis.Response) -> bool:
    """`/serie` cross-parameter rule that OpenAPI cannot express (documented exclusion).

    `inicio > fim`, or a period (explicit or with the defaults of `inicio`/`fim`) longer than
    `MAX_PERIODO_DIAS`, gives 422 although each date is schema-valid on its own. Only for
    that 422 is `positive_data_acceptance` skipped; every other check still runs, so the body
    must still match the documented validation error schema.
    """
    if case.operation.path != "/v1/fundos/{cnpj}/serie" or response.status_code != 422:
        return False
    detail = response.json().get("detail")
    return isinstance(detail, list) and all(
        isinstance(err, dict) and err.get("msg") in PERIOD_RULE_MESSAGES for err in detail
    )


@schema.parametrize()
@settings(
    max_examples=MAX_EXAMPLES,
    derandomize=True,
    database=None,
    deadline=None,
    suppress_health_check=list(HealthCheck),
)
def test_api_conforms_to_openapi(case: schemathesis.Case[Any]) -> None:
    response = case.call(headers={"X-API-Key": CONTRACT_API_KEY})
    excluded: list[CheckFunction] = (
        [positive_data_acceptance] if rejected_by_period_rule(case, response) else []
    )
    case.validate_response(response, excluded_checks=excluded)


def _app(warehouse: Path, **overrides: object) -> FastAPI:
    values: dict[str, object] = {"duckdb_path": warehouse, "api_key": SecretStr(CONTRACT_API_KEY)}
    values.update(overrides)
    return create_app(Settings(_env_file=None, **values))  # type: ignore[call-arg, arg-type]


@pytest.mark.parametrize(
    ("label", "overrides", "headers", "calls", "status"),
    [
        ("GET /v1/fundos", {}, {}, 1, 401),
        ("GET /v1/fundos", {}, {"X-API-Key": "wrong-key"}, 1, 401),
        ("GET /v1/rankings/captacao", {"rate_limit_requests": 1}, None, 2, 429),
        ("GET /v1/fundos/{cnpj}/serie", {"api_key": None}, None, 1, 503),
        ("GET /health", {"duckdb_path": Path("missing/warehouse.duckdb")}, {}, 1, 503),
    ],
)
def test_error_responses_conform_to_openapi(
    contract_warehouse: Path,
    label: str,
    overrides: dict[str, object],
    headers: dict[str, str] | None,
    calls: int,
    status: int,
) -> None:
    """Responses the generated cases never reach (auth, rate limit, outages) are documented."""
    app = _app(contract_warehouse, **overrides)
    operation = schemathesis.openapi.from_asgi("/openapi.json", app).find_operation_by_label(label)
    assert operation is not None
    path_parameters = {"cnpj": "11222333000181"} if "{cnpj}" in label else None
    case = operation.Case(path_parameters=path_parameters)
    sent = {"X-API-Key": CONTRACT_API_KEY} if headers is None else headers
    for _ in range(calls):
        response = case.call(headers=sent)
    assert response.status_code == status
    # The 503s are the expected outcome here, not a server failure; every other check runs
    # (documented status, content type, body schema and the `Retry-After` header schema).
    excluded = [positive_data_acceptance, not_a_server_error]
    case.validate_response(response, excluded_checks=excluded)
    if status == 429:
        (retry_after,) = response.headers["retry-after"]
        assert int(retry_after) >= 1
