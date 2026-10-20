"""API integration tests (task 5.6): every endpoint over a warehouse built by the real dbt models.

The test warehouse is built once per session by `scripts/build_test_warehouse.py`: synthetic raw
rows (`tests/fixtures/warehouse/*.csv`, synthetic CNPJs only) loaded into `raw`, then
`dbt build` of the actual project (models, snapshot and every dbt test). Requests go through
httpx with the ASGI transport (no server, no network) and the results are cross-checked with
direct DuckDB queries on the same marts.

Fixture (current `dim_fundo` rows, latest month 2026-09):

| CNPJ | Kind | Status | Reports | Net inflows 2026-08 / 2026-09 |
|---|---|---|---|---|
| 11222333000181 | class A1 of fund A (FIF) | normal | 2026-08, 2026-09 | 40.00 / 30.00 |
| 11222333000262 | class A2 of fund A, two subclasses | normal | 2026-08, 2026-09 | 20.00 / 154.50 |
| 11444777000242 | fund C (FI) | CANCELADO | 2026-08 only | -200.00 / - |
| 11555666000122 | fund B (FI) | normal | 2026-09 | - / -30.00 |

Run with `make test-integration` (or `pytest -m integration`); excluded from plain `pytest`.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest
from fastapi import FastAPI

from fundos_api.config import Settings
from fundos_api.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ROOT = Path(__file__).resolve().parents[2]
# The one API key every request to /v1/* sends (API_KEY of the app under test).
TEST_API_KEY = "integration-test-key"

CNPJ_A1 = "11222333000181"
CNPJ_A2 = "11222333000262"  # reports per subclass
CNPJ_B = "11555666000122"
CNPJ_C = "11444777000242"  # CANCELADO, no report in the latest month
CNPJ_INEXISTENTE = "99888777000166"
SUB_A, SUB_B = "SUBCLASSE0000A1", "SUBCLASSE0000B2"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def test_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("test_warehouse") / "warehouse.duckdb"
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
def app(test_warehouse: Path) -> FastAPI:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DUCKDB_PATH", str(test_warehouse))
        mp.setenv("API_KEY", TEST_API_KEY)
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers={"X-API-Key": TEST_API_KEY}
    ) as c:
        yield c


def query(warehouse: Path, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    """Direct read-only query on the test warehouse, to cross-check the API."""
    with duckdb.connect(str(warehouse), read_only=True) as con:
        return con.execute(sql, params or []).fetchall()


def cnpjs(body: dict[str, Any]) -> list[str]:
    return [item["cnpj_fundo_classe"] for item in body["items"]]


# --- /health ---------------------------------------------------------------------------------


async def test_health_reports_latest_month(client: httpx.AsyncClient, test_warehouse: Path) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    (latest,) = query(
        test_warehouse, "select max(dt_mes_competencia) from marts.fct_informe_diario"
    )
    assert response.json() == {
        "status": "ok",
        "database": "reachable",
        "latest_month": latest[0].isoformat(),
    }
    assert latest[0].isoformat() == "2026-09-01"


# --- /v1/fundos ------------------------------------------------------------------------------


async def test_fundos_lists_current_versions_without_unknown_member(
    client: httpx.AsyncClient, test_warehouse: Path
) -> None:
    body = (await client.get("/v1/fundos")).json()
    expected = query(
        test_warehouse,
        "select cnpj_fundo_classe from marts.dim_fundo"
        " where fl_versao_atual and tp_registro <> 'DESCONHECIDO' order by 1",
    )
    assert cnpjs(body) == [r[0] for r in expected] == [CNPJ_A1, CNPJ_A2, CNPJ_C, CNPJ_B]
    assert body["total"] == 4
    assert (body["limit"], body["offset"]) == (50, 0)
    by_cnpj = {item["cnpj_fundo_classe"]: item for item in body["items"]}
    assert by_cnpj[CNPJ_A2]["tp_registro"] == "CLASSE"
    assert by_cnpj[CNPJ_A2]["cnpj_fundo"] == "11444777000161"
    assert by_cnpj[CNPJ_A2]["nm_denominacao_social_fundo"] == "FUNDO SINTETICO A"
    assert by_cnpj[CNPJ_B]["tp_registro"] == "FUNDO"
    assert by_cnpj[CNPJ_B]["tp_classe"] is None
    assert by_cnpj[CNPJ_C]["dt_registro"] == "2018-05-02"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"situacao": "cancelado"}, [CNPJ_C]),
        ({"situacao": "EM FUNCIONAMENTO NORMAL"}, [CNPJ_A1, CNPJ_A2, CNPJ_B]),
        ({"informa_recente": "true"}, [CNPJ_A1, CNPJ_A2, CNPJ_B]),
        ({"informa_recente": "false"}, [CNPJ_C]),
        ({"situacao": "CANCELADO", "informa_recente": "true"}, []),
        ({"tp_fundo": "fi"}, [CNPJ_C, CNPJ_B]),
        ({"tp_classe": "classes de cotas de fundos fif"}, [CNPJ_A1, CNPJ_A2]),
        ({"nome": "subclasses"}, [CNPJ_A2]),
        ({"tp_fundo": "FIF", "nome": "sintetica a1"}, [CNPJ_A1]),
    ],
)
async def test_fundos_filters(
    client: httpx.AsyncClient, params: dict[str, str], expected: list[str]
) -> None:
    response = await client.get("/v1/fundos", params=params)
    assert response.status_code == 200
    body = response.json()
    assert cnpjs(body) == expected
    assert body["total"] == len(expected)


async def test_fundos_informa_recente_matches_marts(
    client: httpx.AsyncClient, test_warehouse: Path
) -> None:
    body = (await client.get("/v1/fundos")).json()
    flags = dict(
        query(
            test_warehouse,
            "select cnpj_fundo_classe, fl_informa_recente from marts.dim_fundo"
            " where fl_versao_atual and tp_registro <> 'DESCONHECIDO'",
        )
    )
    assert {i["cnpj_fundo_classe"]: i["fl_informa_recente"] for i in body["items"]} == flags
    assert flags[CNPJ_C] is False


async def test_fundos_pagination(client: httpx.AsyncClient) -> None:
    page = (await client.get("/v1/fundos", params={"limit": 2, "offset": 1})).json()
    assert cnpjs(page) == [CNPJ_A2, CNPJ_C]
    assert (page["limit"], page["offset"], page["total"]) == (2, 1, 4)
    pages = [
        cnpjs((await client.get("/v1/fundos", params={"limit": 3, "offset": o})).json())
        for o in (0, 3)
    ]
    assert pages == [[CNPJ_A1, CNPJ_A2, CNPJ_C], [CNPJ_B]]
    beyond = (await client.get("/v1/fundos", params={"offset": 10})).json()
    assert (beyond["items"], beyond["total"]) == ([], 4)


@pytest.mark.parametrize(
    "params", [{"situacao": "ATIVO"}, {"limit": 0}, {"offset": -1}, {"nome": "ab"}]
)
async def test_fundos_invalid_params_give_422(
    client: httpx.AsyncClient, params: dict[str, object]
) -> None:
    assert (await client.get("/v1/fundos", params=params)).status_code == 422


# --- /v1/fundos/{cnpj}/serie -----------------------------------------------------------------


async def test_serie_default_period_and_json_numbers(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/fundos/{CNPJ_A1}/serie")
    assert response.status_code == 200
    body = response.json()
    # fim = latest reported day of the CNPJ; inicio = 12 months before (inclusive window).
    assert (body["inicio"], body["fim"]) == ("2025-09-03", "2026-09-02")
    assert [p["sk_data"] for p in body["items"]] == ["2026-08-31", "2026-09-01", "2026-09-02"]
    last = body["items"][-1]
    assert last == {
        "sk_data": "2026-09-02",
        "id_subclasse": None,
        "vl_quota": 1.12,
        "vl_patrim_liq": 1030.0,
        "vl_total": 1030.0,
        "vl_captc_dia": 0.0,
        "vl_resg_dia": 10.0,
        "vl_captc_liquida_dia": -10.0,
        "nr_cotst": 3,
    }
    # JSON numbers, not strings (Decimal is serialized as a number).
    assert '"vl_quota":1.12' in response.text
    assert all(isinstance(p["vl_total"], float) for p in body["items"])


async def test_serie_explicit_period(client: httpx.AsyncClient) -> None:
    params = {"inicio": "2026-09-01", "fim": "2026-09-01"}
    body = (await client.get(f"/v1/fundos/{CNPJ_A1}/serie", params=params)).json()
    assert (body["inicio"], body["fim"]) == ("2026-09-01", "2026-09-01")
    assert [(p["sk_data"], p["vl_quota"]) for p in body["items"]] == [("2026-09-01", 1.11)]


async def test_serie_rolls_subclasses_up_into_the_class(
    client: httpx.AsyncClient, test_warehouse: Path
) -> None:
    body = (await client.get(f"/v1/fundos/{CNPJ_A2}/serie")).json()
    day = {p["sk_data"]: p for p in body["items"]}
    assert list(day) == ["2026-08-31", "2026-09-01", "2026-09-02"]
    # Two subclasses on 2026-09-01: amounts summed, share value null, id_subclasse null.
    assert day["2026-09-01"] == {
        "sk_data": "2026-09-01",
        "id_subclasse": None,
        "vl_quota": None,
        "vl_patrim_liq": 310.0,
        "vl_total": 310.0,
        "vl_captc_dia": 110.0,
        "vl_resg_dia": 0.0,
        "vl_captc_liquida_dia": 110.0,
        "nr_cotst": 3,
    }
    # One subclass on 2026-08-31: its share value is kept.
    assert day["2026-08-31"]["vl_quota"] == 1.0
    # The daily series adds up to the monthly fact (RN-01, same marts).
    september = sum(
        Decimal(str(p["vl_captc_liquida_dia"])) for p in body["items"] if p["sk_data"] >= "2026-09"
    )
    ((monthly,),) = query(
        test_warehouse,
        "select vl_captc_liquida_mes from marts.fct_captacao_mensal"
        " where cnpj_fundo_classe = ? and sk_mes = date '2026-09-01'",
        [CNPJ_A2],
    )
    assert september == monthly == Decimal("154.50")


async def test_serie_por_subclasse(client: httpx.AsyncClient, test_warehouse: Path) -> None:
    params = {"por_subclasse": "true", "inicio": "2026-09-01", "fim": "2026-09-30"}
    body = (await client.get(f"/v1/fundos/{CNPJ_A2}/serie", params=params)).json()
    points = [(p["sk_data"], p["id_subclasse"], p["vl_quota"]) for p in body["items"]]
    assert points == [
        ("2026-09-01", SUB_A, 1.01),
        ("2026-09-01", SUB_B, 2.0),
        ("2026-09-02", SUB_A, 1.02),
        ("2026-09-02", SUB_B, 2.05),
    ]
    rows = query(
        test_warehouse,
        "select sk_data, id_subclasse, vl_patrim_liq from marts.fct_informe_diario"
        " where cnpj_fundo_classe = ? and sk_data >= date '2026-09-01'"
        " order by sk_data, id_subclasse",
        [CNPJ_A2],
    )
    assert [(p["sk_data"], p["id_subclasse"], p["vl_patrim_liq"]) for p in body["items"]] == [
        (d.isoformat(), s, float(v)) for d, s, v in rows
    ]


async def test_serie_known_cnpj_without_points_is_empty(client: httpx.AsyncClient) -> None:
    params = {"inicio": "2026-09-01", "fim": "2026-09-30"}
    response = await client.get(f"/v1/fundos/{CNPJ_C}/serie", params=params)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_serie_unknown_cnpj_gives_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/fundos/{CNPJ_INEXISTENTE}/serie")
    assert response.status_code == 404
    assert response.json() == {"detail": "CNPJ not found"}


@pytest.mark.parametrize(
    ("cnpj", "params"),
    [
        (CNPJ_A1, {"inicio": "2026-09-02", "fim": "2026-09-01"}),
        (CNPJ_A1, {"inicio": "2020-01-01", "fim": "2026-09-01"}),
        ("1122233300018", {}),
    ],
)
async def test_serie_invalid_params_give_422(
    client: httpx.AsyncClient, cnpj: str, params: dict[str, str]
) -> None:
    response = await client.get(f"/v1/fundos/{cnpj}/serie", params=params)
    assert response.status_code == 422


# --- /v1/rankings/captacao -------------------------------------------------------------------


async def test_ranking_latest_month_matches_marts(
    client: httpx.AsyncClient, test_warehouse: Path
) -> None:
    response = await client.get("/v1/rankings/captacao")
    assert response.status_code == 200
    body = response.json()
    assert (body["sk_mes"], body["ordem"], body["top"]) == ("2026-09-01", "desc", 10)
    expected = query(
        test_warehouse,
        "select cnpj_fundo_classe, vl_captc_liquida_mes from marts.fct_captacao_mensal"
        " where sk_mes = (select max(sk_mes) from marts.fct_captacao_mensal)"
        " order by vl_captc_liquida_mes desc, cnpj_fundo_classe",
    )
    got = [(i["cnpj_fundo_classe"], i["vl_captc_liquida_mes"]) for i in body["items"]]
    assert got == [(c, float(v)) for c, v in expected]
    assert got == [(CNPJ_A2, 154.5), (CNPJ_A1, 30.0), (CNPJ_B, -30.0)]
    assert [i["posicao"] for i in body["items"]] == [1, 2, 3]
    first = body["items"][0]
    assert first == {
        "cnpj_fundo_classe": CNPJ_A2,
        "nm_denominacao_social": "CLASSE SINTETICA A2 SUBCLASSES",
        "sk_mes": "2026-09-01",
        "vl_captc_mes": 160.0,
        "vl_resg_mes": 5.5,
        "vl_captc_liquida_mes": 154.5,
        "vl_patrim_liq_fim_mes": 355.5,
        "nr_cotst_fim_mes": 4,
        "nr_dias_informados": 2,
        "posicao": 1,
    }


async def test_ranking_month_top_and_ordem(client: httpx.AsyncClient) -> None:
    asc = (await client.get("/v1/rankings/captacao", params={"ordem": "asc"})).json()
    assert cnpjs(asc) == [CNPJ_B, CNPJ_A1, CNPJ_A2]
    august = (await client.get("/v1/rankings/captacao", params={"mes": "2026-08", "top": 2})).json()
    assert (august["sk_mes"], august["top"]) == ("2026-08-01", 2)
    assert cnpjs(august) == [CNPJ_A1, CNPJ_A2]
    outflows = (
        await client.get(
            "/v1/rankings/captacao", params={"mes": "2026-08", "ordem": "asc", "top": 1}
        )
    ).json()
    item = outflows["items"][0]
    # A cancelled fund keeps its ranking in the months it reported.
    assert (item["cnpj_fundo_classe"], item["vl_captc_liquida_mes"]) == (CNPJ_C, -200.0)
    assert item["nm_denominacao_social"] == "FUNDO SINTETICO C CANCELADO"


async def test_ranking_month_without_data_gives_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/rankings/captacao", params={"mes": "2026-07"})
    assert response.status_code == 404
    assert response.json() == {"detail": "no data for month 2026-07"}


@pytest.mark.parametrize(
    "params", [{"top": 0}, {"top": 101}, {"ordem": "up"}, {"mes": "2026-13"}, {"mes": "2026-9"}]
)
async def test_ranking_invalid_params_give_422(
    client: httpx.AsyncClient, params: dict[str, object]
) -> None:
    assert (await client.get("/v1/rankings/captacao", params=params)).status_code == 422
