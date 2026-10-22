"""Input validation with Pydantic: pagination bounds and CNPJ format (422 on invalid input)."""

from typing import Annotated

import pytest
from conftest import api_client
from fastapi import Depends
from fastapi.testclient import TestClient

from fundos_api.config import Settings
from fundos_api.main import create_app
from fundos_api.params import CnpjPath, PageParams, pagination


@pytest.fixture
def probe(settings: Settings) -> TestClient:
    """App plus test-only routes that use the shared input dependencies (endpoints: 5.2-5.4)."""
    app = create_app(settings.model_copy(update={"default_page_size": 20, "max_page_size": 100}))

    @app.get("/_page")
    def page(params: Annotated[PageParams, Depends(pagination)]) -> PageParams:
        return params

    @app.get("/_fundo/{cnpj}")
    def fundo(cnpj: CnpjPath) -> dict[str, str]:
        return {"cnpj": cnpj}

    return api_client(app)


def test_pagination_defaults(probe: TestClient) -> None:
    assert probe.get("/_page").json() == {"limit": 20, "offset": 0}


def test_pagination_valid(probe: TestClient) -> None:
    assert probe.get("/_page?limit=100&offset=40").json() == {"limit": 100, "offset": 40}


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=abc",
        "limit=101",  # above max_page_size of the settings
        "limit=5000",  # above the hard cap
        "offset=-1",
        "offset=1000001",
        "limit=10&offset=x",
    ],
)
def test_pagination_invalid_is_422(probe: TestClient, query: str) -> None:
    response = probe.get(f"/_page?{query}")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "query"


def test_pagination_ignores_unknown_params(probe: TestClient) -> None:
    """Unknown query parameters are ignored (API-wide rule), so filters can sit beside it."""
    assert probe.get("/_page?limit=5&situacao=x&other=1").json() == {"limit": 5, "offset": 0}


def test_cnpj_valid(probe: TestClient) -> None:
    assert probe.get("/_fundo/11222333000181").json() == {"cnpj": "11222333000181"}


@pytest.mark.parametrize(
    "cnpj", ["1122233300018", "112223330001811", "11.222.333-0001-81", "1122233300018a"]
)
def test_cnpj_invalid_is_422(probe: TestClient, cnpj: str) -> None:
    response = probe.get(f"/_fundo/{cnpj}")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "cnpj"]


def test_openapi_limit_maximum_is_the_configured_page_size(settings: Settings) -> None:
    """Contract (6.1): the documented `limit` maximum is `MAX_PAGE_SIZE`, not the hard cap."""
    app = create_app(settings.model_copy(update={"max_page_size": 200}))
    document = app.openapi()
    (limit,) = [
        p for p in document["paths"]["/v1/fundos"]["get"]["parameters"] if p["name"] == "limit"
    ]
    assert [o["maximum"] for o in limit["schema"]["anyOf"] if "maximum" in o] == [200]
    assert app.openapi() is document


@pytest.mark.parametrize("value", ["0", "1700000000", "2026-9-1", "2026-09-01T00:00:00"])
def test_serie_dates_must_be_iso(client: TestClient, value: str) -> None:
    """Contract (6.1): `format: date` only; Unix timestamps were accepted before."""
    response = client.get(f"/v1/fundos/11222333000181/serie?fim={value}")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "fim"]


def test_month_zero_is_422(client: TestClient) -> None:
    """Contract (6.1): `mes=0000-01` gave a 500 (year 0 is not a date)."""
    assert client.get("/v1/rankings/captacao?mes=0000-01").status_code == 422


def test_openapi_situacao_is_an_enum(client: TestClient) -> None:
    params = client.get("/openapi.json").json()["paths"]["/v1/fundos"]["get"]["parameters"]
    (situacao,) = [p for p in params if p["name"] == "situacao"]
    enum = situacao["schema"].get("enum") or next(
        o["enum"] for o in situacao["schema"]["anyOf"] if "enum" in o
    )
    assert "CANCELADO" in enum and "EM FUNCIONAMENTO NORMAL" in enum
