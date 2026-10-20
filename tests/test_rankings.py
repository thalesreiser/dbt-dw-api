"""`GET /v1/rankings/captacao` (RF-09): top N of the month by net inflows (RN-01)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from conftest import CNPJ_CLASSE, api_client, build_warehouse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fundos_api import schemas
from fundos_api.config import Settings
from fundos_api.main import create_app

# Synthetic CNPJs with valid check digits; they do not belong to real funds.
CNPJ_A = "11222333000262"  # 2026-09: net +20, has an older dim_fundo version
CNPJ_B = "11222333000343"  # 2026-09: net +5, ties with CNPJ_CLASSE (net +5 in conftest)
CNPJ_C = "11222333000424"  # 2026-09: net -30, not in dim_fundo
CNPJ_D = "11222333000505"  # 2026-08 only

EXTRA_ROWS = f"""
insert into marts.dim_fundo (sk_fundo, cnpj_fundo_classe, tp_registro, nm_denominacao_social,
    sit_fundo_classe, dt_valido_de, dt_valido_ate, fl_versao_atual) values
    ('skA0', '{CNPJ_A}', 'CLASSE', 'CLASSE A ANTIGA', 'EM FUNCIONAMENTO NORMAL',
     '1900-01-01', '2026-09-15', false),
    ('skA1', '{CNPJ_A}', 'CLASSE', 'CLASSE A', 'EM FUNCIONAMENTO NORMAL',
     '2026-09-15', null, true),
    ('skB', '{CNPJ_B}', 'CLASSE', 'CLASSE B', 'EM FUNCIONAMENTO NORMAL',
     '1900-01-01', null, true),
    ('skD', '{CNPJ_D}', 'CLASSE', 'CLASSE D', 'EM FUNCIONAMENTO NORMAL',
     '1900-01-01', null, true);
insert into marts.fct_captacao_mensal values
    ('skA0', '2026-09-01', '{CNPJ_A}', 20.50, 0.50, 20.00, 1000.10, 7, '2026-09-30', 21),
    ('skB', '2026-09-01', '{CNPJ_B}', 7, 2, 5, null, null, '2026-09-30', 21),
    ('-1', '2026-09-01', '{CNPJ_C}', 0, 30, -30, 0, 0, '2026-09-30', 21),
    ('skD', '2026-08-01', '{CNPJ_D}', 1, 0, 1, 10, 1, '2026-08-31', 21);
"""

URL = "/v1/rankings/captacao"


@pytest.fixture
def rk(tmp_path: Path) -> TestClient:
    path = build_warehouse(tmp_path / "warehouse.duckdb")
    con = duckdb.connect(str(path))
    try:
        con.execute(EXTRA_ROWS)
    finally:
        con.close()
    return api_client(create_app(Settings(duckdb_path=path, _env_file=None)))  # type: ignore[call-arg]


def _cnpjs(body: dict[str, object]) -> list[str]:
    items = body["items"]
    assert isinstance(items, list)
    return [i["cnpj_fundo_classe"] for i in items]


def test_default_month_is_latest_and_ordered_desc(rk: TestClient) -> None:
    resp = rk.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sk_mes"] == "2026-09-01"
    assert body["ordem"] == "desc"
    assert body["top"] == 10
    # Tie at +5 is broken by CNPJ ascending.
    assert _cnpjs(body) == [CNPJ_A, CNPJ_CLASSE, CNPJ_B, CNPJ_C]
    assert [i["posicao"] for i in body["items"]] == [1, 2, 3, 4]


def test_item_fields_current_name_and_json_numbers(rk: TestClient) -> None:
    first, _, third, last = rk.get(URL, params={"mes": "2026-09"}).json()["items"]
    assert first == {
        "posicao": 1,
        "cnpj_fundo_classe": CNPJ_A,
        "nm_denominacao_social": "CLASSE A",  # current dim_fundo version, not the fact's
        "sk_mes": "2026-09-01",
        "vl_captc_mes": 20.5,
        "vl_resg_mes": 0.5,
        "vl_captc_liquida_mes": 20.0,
        "vl_patrim_liq_fim_mes": 1000.1,
        "nr_cotst_fim_mes": 7,
        "nr_dias_informados": 21,
    }
    assert third["vl_patrim_liq_fim_mes"] is None
    assert last["nm_denominacao_social"] is None  # no dim_fundo row
    assert last["vl_captc_liquida_mes"] == -30.0


def test_ordem_asc_lists_largest_outflows_first(rk: TestClient) -> None:
    body = rk.get(URL, params={"ordem": "asc"}).json()
    assert _cnpjs(body) == [CNPJ_C, CNPJ_CLASSE, CNPJ_B, CNPJ_A]


def test_top_limits_and_explicit_month(rk: TestClient) -> None:
    assert _cnpjs(rk.get(URL, params={"top": 2}).json()) == [CNPJ_A, CNPJ_CLASSE]
    body = rk.get(URL, params={"mes": "2026-08", "top": 1}).json()
    assert body["sk_mes"] == "2026-08-01"
    assert _cnpjs(body) == [CNPJ_D]
    assert len(rk.get(URL, params={"top": 100}).json()["items"]) == 4


@pytest.mark.parametrize(
    "params",
    [
        {"top": 0},
        {"top": 101},
        {"top": "x"},
        {"mes": "2026-13"},
        {"mes": "2026-9"},
        {"mes": "2026-09-01"},
        {"mes": "09-2026"},
        {"mes": "2026-09' or 1=1 --"},
        {"ordem": "up"},
    ],
)
def test_invalid_params_give_422(rk: TestClient, params: dict[str, object]) -> None:
    assert rk.get(URL, params=params).status_code == 422


def test_month_without_data_gives_404(rk: TestClient) -> None:
    resp = rk.get(URL, params={"mes": "2026-07"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "no data for month 2026-07"}


def test_empty_warehouse_gives_404(tmp_path: Path) -> None:
    path = build_warehouse(tmp_path / "empty.duckdb", with_rows=False)
    app = create_app(Settings(duckdb_path=path, _env_file=None))  # type: ignore[call-arg]
    resp = api_client(app).get(URL)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "no monthly data available"}


def test_missing_warehouse_gives_503(tmp_path: Path) -> None:
    app = create_app(Settings(duckdb_path=tmp_path / "none.duckdb", _env_file=None))  # type: ignore[call-arg]
    resp = api_client(app).get(URL)
    assert resp.status_code == 503
    assert "none.duckdb" not in resp.text


@pytest.mark.parametrize("model", [schemas.RankingCaptacao, schemas.RankingCaptacaoItem])
def test_no_personal_data_in_ranking(model: type[BaseModel]) -> None:
    """LGPD: same rule as `test_schemas_config.py` for the ranking schemas."""
    for name in model.model_fields:
        assert "cpf" not in name
        assert "gestor" not in name
        assert "cotista" not in name
