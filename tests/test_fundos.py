"""`GET /v1/fundos`: filters, pagination, 422 on invalid input, read-only (RF-07)."""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from conftest import CNPJ_CLASSE, api_client
from fastapi.testclient import TestClient

from fundos_api.config import Settings
from fundos_api.main import create_app
from fundos_api.routers.fundos import SITUACOES


def _cnpj(base: str) -> str:
    """Synthetic CNPJ with valid check digits from a 12-digit base."""
    digits = [int(c) for c in base]
    for weights in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        rest = sum(d * w for d, w in zip(digits, weights, strict=True)) % 11
        digits.append(0 if rest < 2 else 11 - rest)
    return "".join(map(str, digits))


CNPJ_FIDC = _cnpj("223334440001")
CNPJ_LIQ = _cnpj("334445550001")
CNPJ_CANCELADO = _cnpj("445556660001")
CNPJ_CANCELADO_INATIVO = _cnpj("556667770001")


def _row(
    cnpj: str,
    tp_registro: str,
    nome: str,
    tp_fundo: str | None,
    tp_classe: str | None,
    situacao: str,
    atual: bool = True,
    valido_de: str = "1900-01-01",
    informa: bool = False,
) -> str:
    def q(value: str | None) -> str:
        return "null" if value is None else f"'{value}'"

    valido_ate = "null" if atual else "'2026-09-01'"
    return (
        f"('sk_{cnpj}_{valido_de}', '{cnpj}', '{tp_registro}', null, null, null, '{nome}', null, "
        f"{q(tp_fundo)}, {q(tp_classe)}, '{situacao}', '{situacao}', null, null, null, null, "
        f"null, null, null, null, null, null, {str(informa).lower()}, '{valido_de}', "
        f"{valido_ate}, {str(atual).lower()})"
    )


EXTRA_ROWS = [
    _row("00000000000000", "DESCONHECIDO", "DESCONHECIDO", None, None, "DESCONHECIDO"),
    _row(
        CNPJ_CLASSE,
        "CLASSE",
        "CLASSE TESTE ANTIGA",
        "FIF",
        "Classes de Cotas",
        "FASE PRE-OPERACIONAL",
        atual=False,
        valido_de="1800-01-01",
    ),
    _row(
        CNPJ_FIDC,
        "CLASSE",
        "RECEBIVEIS SINTETICOS",
        "FIDC",
        "CLASSES DE COTAS DE FUNDOS FIDC",
        "EM FUNCIONAMENTO NORMAL",
    ),
    _row(CNPJ_LIQ, "CLASSE", "CLASSE EM LIQUIDACAO", "FIF", "Classes de Cotas", "EM LIQUIDACAO"),
    _row(
        CNPJ_CANCELADO,
        "FUNDO",
        "FUNDO CANCELADO QUE INFORMA",
        "FI",
        None,
        "CANCELADO",
        informa=True,
    ),
    _row(CNPJ_CANCELADO_INATIVO, "FUNDO", "FUNDO CANCELADO SEM INFORME", "FI", None, "CANCELADO"),
]
CURRENT = sorted([CNPJ_CLASSE, CNPJ_FIDC, CNPJ_LIQ, CNPJ_CANCELADO, CNPJ_CANCELADO_INATIVO])


@pytest.fixture
def fundos_client(warehouse: Path, settings: Settings) -> TestClient:
    con = duckdb.connect(str(warehouse))
    try:
        con.execute("insert into marts.dim_fundo values " + ", ".join(EXTRA_ROWS))
    finally:
        con.close()
    return api_client(create_app(settings))


def _get(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/v1/fundos", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _cnpjs(body: dict[str, Any]) -> list[str]:
    return [item["cnpj_fundo_classe"] for item in body["items"]]


def test_lists_current_versions_without_unknown_member_by_cnpj(fundos_client: TestClient) -> None:
    body = _get(fundos_client)
    assert _cnpjs(body) == CURRENT
    assert body["total"] == 5
    assert body["limit"] == 50
    assert body["offset"] == 0
    classe = next(i for i in body["items"] if i["cnpj_fundo_classe"] == CNPJ_CLASSE)
    assert classe["nm_denominacao_social"] == "CLASSE TESTE"
    assert classe["sit_fundo_classe"] == "EM FUNCIONAMENTO NORMAL"
    assert classe["fl_informa_recente"] is True


@pytest.mark.parametrize("situacao", ["EM FUNCIONAMENTO NORMAL", "em funcionamento normal"])
def test_filter_by_status_is_case_insensitive(fundos_client: TestClient, situacao: str) -> None:
    body = _get(fundos_client, situacao=situacao)
    assert _cnpjs(body) == sorted([CNPJ_CLASSE, CNPJ_FIDC])
    assert body["total"] == 2
    assert {i["sit_fundo_classe"] for i in body["items"]} == {"EM FUNCIONAMENTO NORMAL"}


def test_cancelled_fund_that_reports_is_listed_as_cancelled(fundos_client: TestClient) -> None:
    body = _get(fundos_client, situacao="CANCELADO")
    assert _cnpjs(body) == sorted([CNPJ_CANCELADO, CNPJ_CANCELADO_INATIVO])
    assert {i["tp_registro"] for i in body["items"]} == {"FUNDO"}


def test_filter_cancelled_that_still_report(fundos_client: TestClient) -> None:
    body = _get(fundos_client, situacao="CANCELADO", informa_recente="true")
    assert _cnpjs(body) == [CNPJ_CANCELADO]
    assert body["items"][0]["fl_informa_recente"] is True
    quiet = _get(fundos_client, situacao="CANCELADO", informa_recente="false")
    assert _cnpjs(quiet) == [CNPJ_CANCELADO_INATIVO]
    assert _cnpjs(_get(fundos_client, informa_recente="true")) == sorted(
        [CNPJ_CLASSE, CNPJ_CANCELADO]
    )


def test_filters_combine_with_pagination_and_ignore_unknown_params(
    fundos_client: TestClient,
) -> None:
    first = _get(fundos_client, tp_fundo="FIF", informa_recente="false", limit=1, unknown="x")
    second = _get(fundos_client, tp_fundo="FIF", informa_recente="false", limit=1, offset=1)
    assert _cnpjs(first) == [CNPJ_LIQ]
    assert second["items"] == []
    assert first["total"] == second["total"] == 1
    everything = _get(fundos_client, situacao="CANCELADO", limit=1, offset=1)
    assert _cnpjs(everything) == sorted([CNPJ_CANCELADO, CNPJ_CANCELADO_INATIVO])[1:]
    assert everything["total"] == 2


def test_old_version_status_does_not_match(fundos_client: TestClient) -> None:
    body = _get(fundos_client, situacao="FASE PRE-OPERACIONAL")
    assert body == {"items": [], "limit": 50, "offset": 0, "total": 0}


def test_filter_by_fund_and_class_type(fundos_client: TestClient) -> None:
    assert _cnpjs(_get(fundos_client, tp_fundo="fif")) == sorted([CNPJ_CLASSE, CNPJ_LIQ])
    assert _cnpjs(_get(fundos_client, tp_classe="classes de cotas de fundos fidc")) == [CNPJ_FIDC]
    both = _get(fundos_client, tp_fundo="FIF", situacao="EM LIQUIDACAO")
    assert _cnpjs(both) == [CNPJ_LIQ]


def test_filter_by_name_substring(fundos_client: TestClient) -> None:
    assert _cnpjs(_get(fundos_client, nome="sintetic")) == [CNPJ_FIDC]
    assert _get(fundos_client, nome="100%_x")["total"] == 0


def test_pagination_pages_and_total(fundos_client: TestClient) -> None:
    first = _get(fundos_client, limit=2)
    second = _get(fundos_client, limit=2, offset=2)
    beyond = _get(fundos_client, limit=2, offset=10)
    assert _cnpjs(first) == CURRENT[:2]
    assert _cnpjs(second) == CURRENT[2:4]
    assert first["total"] == second["total"] == beyond["total"] == 5
    assert beyond["items"] == []
    assert (second["limit"], second["offset"]) == (2, 2)


@pytest.mark.parametrize(
    "params",
    [
        {"situacao": "ATIVO"},
        {"situacao": "DESCONHECIDO"},
        {"tp_fundo": "FI'; drop table x"},
        {"tp_classe": ""},
        {"nome": "ab"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"informa_recente": "maybe"},
        {"situacao": "CANCELADO", "limit": "abc"},
    ],
)
def test_invalid_input_is_422(fundos_client: TestClient, params: dict[str, Any]) -> None:
    response = fundos_client.get("/v1/fundos", params=params)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "query"


def test_status_domain_matches_mart_values() -> None:
    assert "DESCONHECIDO" not in SITUACOES
    assert {"CANCELADO", "EM FUNCIONAMENTO NORMAL", "EM LIQUIDACAO"} <= SITUACOES


def test_empty_dimension_returns_empty_page(tmp_path: Path) -> None:
    from conftest import build_warehouse

    path = build_warehouse(tmp_path / "empty.duckdb", with_rows=False)
    client = api_client(create_app(Settings(duckdb_path=path, _env_file=None)))  # type: ignore[call-arg]
    assert _get(client) == {"items": [], "limit": 50, "offset": 0, "total": 0}


def test_missing_warehouse_is_503_and_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "missing.duckdb"
    client = api_client(create_app(Settings(duckdb_path=path, _env_file=None)))  # type: ignore[call-arg]
    response = client.get("/v1/fundos")
    assert response.status_code == 503
    assert str(tmp_path) not in response.text
    assert not path.exists()


def test_read_only_warehouse_unchanged(fundos_client: TestClient, warehouse: Path) -> None:
    before = warehouse.read_bytes()
    _get(fundos_client, situacao="CANCELADO")
    _get(fundos_client, nome="teste", limit=1)
    assert warehouse.read_bytes() == before


def test_openapi_documents_filters_without_personal_data(fundos_client: TestClient) -> None:
    spec = fundos_client.get("/openapi.json").json()
    names = {p["name"] for p in spec["paths"]["/v1/fundos"]["get"]["parameters"]}
    assert names == {
        "situacao",
        "tp_fundo",
        "tp_classe",
        "nome",
        "informa_recente",
        "limit",
        "offset",
    }
    fields = spec["components"]["schemas"]["FundoResumo"]["properties"]
    assert not any("cpf" in f or "gestor" in f for f in fields)
