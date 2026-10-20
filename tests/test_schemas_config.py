"""Response schemas (LGPD guard, mapping from the marts) and settings."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from conftest import CNPJ_CLASSE
from pydantic import BaseModel, ValidationError

from fundos_api import schemas
from fundos_api.config import Settings
from fundos_api.db import connect_read_only

RESPONSE_MODELS: list[type[BaseModel]] = [
    schemas.HealthResponse,
    schemas.ErrorResponse,
    schemas.FundoResumo,
    schemas.PontoSerie,
    schemas.CaptacaoMensal,
    schemas.Page[schemas.FundoResumo],
]


@pytest.mark.parametrize("model", RESPONSE_MODELS)
def test_no_personal_data_in_responses(model: type[BaseModel]) -> None:
    """LGPD: no CPF and no natural-person name (manager, shareholder) in any response."""
    for name in model.model_fields:
        assert "cpf" not in name
        assert "gestor" not in name
        assert "cotista" not in name


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    cursor = con.execute(sql)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def test_schemas_validate_mart_rows(warehouse: Path) -> None:
    fundo_cols = ", ".join(schemas.FundoResumo.model_fields)
    with connect_read_only(warehouse) as con:
        (fundo,) = _rows(con, f"select {fundo_cols} from marts.dim_fundo where fl_versao_atual")
        serie_cols = ", ".join(schemas.PontoSerie.model_fields)
        serie = _rows(con, f"select {serie_cols} from marts.fct_informe_diario order by sk_data")
        (mensal,) = _rows(
            con,
            "select f.*, d.nm_denominacao_social from marts.fct_captacao_mensal f "
            "join marts.dim_fundo d using (sk_fundo)",
        )
    resumo = schemas.FundoResumo.model_validate(fundo)
    assert resumo.cnpj_fundo_classe == CNPJ_CLASSE
    pontos = [schemas.PontoSerie.model_validate(r) for r in serie]
    assert pontos[0].vl_quota == Decimal("1.5")
    payload = {k: v for k, v in mensal.items() if k in schemas.CaptacaoMensal.model_fields}
    captacao = schemas.CaptacaoMensal.model_validate(payload)
    assert captacao.vl_captc_liquida_mes == captacao.vl_captc_mes - captacao.vl_resg_mes
    page = schemas.Page[schemas.PontoSerie](items=pontos, limit=10, offset=0, total=2)
    dumped = page.model_dump(mode="json")["items"][1]
    assert dumped["vl_patrim_liq"] == 110.0
    assert isinstance(dumped["vl_quota"], float)
    assert page.model_dump()["items"][1]["vl_patrim_liq"] == Decimal("110.00")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1500.25", 1500.25), ("1500.255", 1500.26), ("0.125", 0.12), ("-30", -30.0)],
)
def test_amounts_serialized_as_numbers_with_2_decimals(value: str, expected: float) -> None:
    ponto = schemas.PontoSerie(
        sk_data=date(2026, 9, 1),
        vl_quota=Decimal("1.123456789012"),
        vl_captc_liquida_dia=Decimal(value),
    )
    dumped = ponto.model_dump(mode="json")
    assert dumped["vl_captc_liquida_dia"] == expected
    assert dumped["vl_quota"] == 1.123456789012  # share value: not rounded
    assert ponto.model_dump()["vl_captc_liquida_dia"] == Decimal(value)  # exact internally


def test_schemas_reject_unknown_fields_and_bad_cnpj() -> None:
    with pytest.raises(ValidationError):
        schemas.ErrorResponse(detail="x", path="/secret")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        schemas.FundoResumo(
            cnpj_fundo_classe="123",
            tp_registro="CLASSE",
            nm_denominacao_social="X",
            sit_fundo_classe="EM FUNCIONAMENTO NORMAL",
            fl_informa_recente=False,
        )


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("MAX_PAGE_SIZE", "200")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.duckdb_path == tmp_path / "w.duckdb"
    assert settings.max_page_size == 200
    assert settings.api_prefix == "/v1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"default_page_size": 600, "max_page_size": 500},
        {"max_page_size": 5000},
        {"marts_schema": "marts; drop table x"},
        {"api_prefix": "v1"},
    ],
)
def test_settings_reject_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)  # type: ignore[arg-type]
