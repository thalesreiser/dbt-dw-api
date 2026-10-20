"""`GET /v1/fundos/{cnpj}/serie` (RF-08): period, ordering, 404 vs empty, validation."""

from datetime import date
from pathlib import Path

import duckdb
import pytest
from conftest import CNPJ_CLASSE, CNPJ_FUNDO, build_warehouse
from fastapi.testclient import TestClient

from fundos_api import schemas
from fundos_api.config import Settings
from fundos_api.main import create_app
from fundos_api.routers.serie import MAX_PERIODO_DIAS, default_inicio, months_before

# Synthetic CNPJs (valid check digits, not real funds).
CNPJ_SUBCLASSES = "11222333000262"  # class reported per subclass
CNPJ_SEM_INFORME = "11444777000242"  # in dim_fundo (old version only), no daily reports
CNPJ_INEXISTENTE = "99888777000166"

EXTRA_ROWS = f"""
insert into marts.dim_fundo (sk_fundo, cnpj_fundo_classe, tp_registro, nm_denominacao_social,
    sit_fundo_classe, dt_valido_de, dt_valido_ate, fl_versao_atual) values
    ('sk2', '{CNPJ_SUBCLASSES}', 'CLASSE', 'CLASSE SUB', 'EM FUNCIONAMENTO NORMAL',
     '1900-01-01', null, true),
    ('sk3', '{CNPJ_SEM_INFORME}', 'CLASSE', 'CLASSE ANTIGA', 'CANCELADA',
     '1900-01-01', '2026-01-01', false),
    ('sk-1', '00000000000000', 'DESCONHECIDO', 'DESCONHECIDO', 'DESCONHECIDO',
     '1900-01-01', null, true);
insert into marts.fct_informe_diario values
    ('sk2', '2026-09-02', '{CNPJ_SUBCLASSES}', 'B', 50.50, 2.0, 50.50, 1, 0, 1, 2,
     '2026-09-01', '2026-10-01'),
    ('sk2', '2026-09-02', '{CNPJ_SUBCLASSES}', 'A', 100.25, 1.0, 100.25, 3, 1, 2, 5,
     '2026-09-01', '2026-10-01'),
    ('sk2', '2026-08-03', '{CNPJ_SUBCLASSES}', 'A', 90, 0.9, 90, 0, 0, 0, 5,
     '2026-08-01', '2026-09-01'),
    ('sk2', '2025-08-03', '{CNPJ_SUBCLASSES}', 'A', 10, 0.1, 10, 0, 0, 0, 1,
     '2025-08-01', '2025-09-01');
"""


@pytest.fixture
def api(tmp_path: Path) -> TestClient:
    path = build_warehouse(tmp_path / "warehouse.duckdb")
    con = duckdb.connect(str(path))
    try:
        con.execute(EXTRA_ROWS)
    finally:
        con.close()
    settings = Settings(duckdb_path=path, _env_file=None)  # type: ignore[call-arg]
    return TestClient(create_app(settings))


def _url(cnpj: str) -> str:
    return f"/v1/fundos/{cnpj}/serie"


def test_series_ordered_with_decimal_strings(client: TestClient) -> None:
    response = client.get(_url(CNPJ_CLASSE), params={"inicio": "2026-08-01", "fim": "2026-09-30"})
    assert response.status_code == 200
    body = response.json()
    assert body["cnpj_fundo_classe"] == CNPJ_CLASSE
    assert (body["inicio"], body["fim"]) == ("2026-08-01", "2026-09-30")
    assert [p["sk_data"] for p in body["items"]] == ["2026-08-31", "2026-09-01"]
    first = body["items"][0]
    # Decimals are exact JSON strings, as in the skeleton's schemas.
    assert first["vl_patrim_liq"] == "100.00"
    assert first["vl_quota"] == "1.500000000000"
    assert first["vl_captc_liquida_dia"] == "8.00"
    assert first["nr_cotst"] == 3
    assert first["id_subclasse"] is None


def test_period_filter_is_inclusive(client: TestClient) -> None:
    response = client.get(_url(CNPJ_CLASSE), params={"inicio": "2026-09-01", "fim": "2026-09-01"})
    assert [p["sk_data"] for p in response.json()["items"]] == ["2026-09-01"]


def test_default_period_is_last_12_months_of_the_cnpj(api: TestClient) -> None:
    body = api.get(_url(CNPJ_SUBCLASSES)).json()
    assert (body["inicio"], body["fim"]) == ("2025-09-03", "2026-09-02")
    assert [p["sk_data"] for p in body["items"]] == ["2026-08-03", "2026-09-02"]


def test_only_inicio_extends_to_latest(api: TestClient) -> None:
    body = api.get(_url(CNPJ_SUBCLASSES), params={"inicio": "2025-01-01"}).json()
    assert body["fim"] == "2026-09-02"
    assert [p["sk_data"] for p in body["items"]] == ["2025-08-03", "2026-08-03", "2026-09-02"]


def test_inicio_after_latest_gives_empty(api: TestClient) -> None:
    body = api.get(_url(CNPJ_SUBCLASSES), params={"inicio": "2026-10-01"}).json()
    assert (body["inicio"], body["fim"], body["items"]) == ("2026-10-01", "2026-10-01", [])


def test_only_fim(api: TestClient) -> None:
    body = api.get(_url(CNPJ_SUBCLASSES), params={"fim": "2026-08-31"}).json()
    assert body["inicio"] == "2025-09-01"
    assert [p["sk_data"] for p in body["items"]] == ["2026-08-03"]


def test_subclasses_rolled_up_to_class(api: TestClient) -> None:
    body = api.get(_url(CNPJ_SUBCLASSES), params={"inicio": "2026-09-02", "fim": "2026-09-02"})
    (point,) = body.json()["items"]
    assert point["vl_patrim_liq"] == "150.75"
    assert point["vl_captc_dia"] == "4.00"
    assert point["vl_resg_dia"] == "1.00"
    assert point["vl_captc_liquida_dia"] == "3.00"
    assert point["nr_cotst"] == 7
    assert point["vl_quota"] is None  # share values of two subclasses are not additive
    assert point["id_subclasse"] is None


def test_unknown_cnpj_is_404(api: TestClient) -> None:
    response = api.get(_url(CNPJ_INEXISTENTE))
    assert response.status_code == 404
    assert response.json() == {"detail": "CNPJ not found"}


def test_unknown_member_is_404(api: TestClient) -> None:
    assert api.get(_url("00000000000000")).status_code == 404


def test_known_cnpj_without_points_is_empty(api: TestClient) -> None:
    """Any dim_fundo version counts (here only an expired one); no reports -> 200 and []."""
    response = api.get(_url(CNPJ_SEM_INFORME), params={"inicio": "2026-01-01"})
    assert response.status_code == 200
    assert response.json()["items"] == []
    no_params = api.get(_url(CNPJ_SEM_INFORME))
    assert no_params.status_code == 200
    assert no_params.json()["fim"] == date.today().isoformat()


def test_parent_fund_cnpj_without_own_row_is_404(client: TestClient) -> None:
    # CNPJ_FUNDO is not a row of dim_fundo in the base fixture: 404.
    assert client.get(_url(CNPJ_FUNDO)).status_code == 404


@pytest.mark.parametrize("cnpj", ["1122233300018", "112223330001811", "11.222.333-0001-81", "abc"])
def test_invalid_cnpj_is_422(client: TestClient, cnpj: str) -> None:
    assert client.get(_url(cnpj)).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"inicio": "2026-09-02", "fim": "2026-09-01"},
        {"inicio": "2020-01-01", "fim": "2026-09-01"},
        {"inicio": "2026-13-01"},
        {"fim": "not-a-date"},
    ],
)
def test_invalid_period_is_422(client: TestClient, params: dict[str, str]) -> None:
    assert client.get(_url(CNPJ_CLASSE), params=params).status_code == 422


def test_invalid_period_checked_before_404(client: TestClient) -> None:
    params = {"inicio": "2026-09-02", "fim": "2026-09-01"}
    assert client.get(_url(CNPJ_INEXISTENTE), params=params).status_code == 422


def test_old_inicio_without_fim_exceeds_max(api: TestClient) -> None:
    response = api.get(_url(CNPJ_SUBCLASSES), params={"inicio": "2010-01-01"})
    assert response.status_code == 422
    assert str(MAX_PERIODO_DIAS) in response.text


def test_max_period_accepted(client: TestClient) -> None:
    fim = date(2026, 9, 1)
    inicio = date.fromordinal(fim.toordinal() - MAX_PERIODO_DIAS + 1)
    params = {"inicio": inicio.isoformat(), "fim": fim.isoformat()}
    assert client.get(_url(CNPJ_CLASSE), params=params).status_code == 200


def test_warehouse_unavailable_is_503(tmp_path: Path) -> None:
    settings = Settings(duckdb_path=tmp_path / "missing.duckdb", _env_file=None)  # type: ignore[call-arg]
    response = TestClient(create_app(settings)).get(_url(CNPJ_CLASSE))
    assert response.status_code == 503
    assert "missing" not in response.text


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 2), date(2025, 9, 2)),
        (date(2024, 2, 29), date(2023, 2, 28)),
        (date(2026, 3, 31), date(2025, 3, 31)),
        (date(2026, 1, 15), date(2025, 1, 15)),
    ],
)
def test_months_before_12(day: date, expected: date) -> None:
    assert months_before(day, 12) == expected


def test_months_before_clamps_month_end() -> None:
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert default_inicio(date(2026, 3, 31)) == date(2025, 4, 1)


def test_openapi_documents_route() -> None:
    spec = create_app(Settings(_env_file=None)).openapi()  # type: ignore[call-arg]
    operation = spec["paths"]["/v1/fundos/{cnpj}/serie"]["get"]
    assert {p["name"] for p in operation["parameters"]} == {"cnpj", "inicio", "fim"}
    assert "404" in operation["responses"]


def test_no_personal_data_in_serie_schema() -> None:
    for name in schemas.SerieFundo.model_fields:
        assert "cpf" not in name and "gestor" not in name and "cotista" not in name
