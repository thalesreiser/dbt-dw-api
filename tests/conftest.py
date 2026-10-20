"""Shared fixtures: a tiny synthetic warehouse with the marts the API reads (no real data)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from fundos_api.config import Settings
from fundos_api.main import create_app

# Synthetic CNPJs with valid check digits; they do not belong to real funds.
CNPJ_CLASSE = "11222333000181"
CNPJ_FUNDO = "11444777000161"

MARTS_DDL = """
create schema marts;
create table marts.dim_fundo (
    sk_fundo varchar, cnpj_fundo_classe varchar, tp_registro varchar,
    id_registro_classe varchar, id_registro_fundo varchar, cnpj_fundo varchar,
    nm_denominacao_social varchar, nm_denominacao_social_fundo varchar, tp_fundo varchar,
    tp_classe varchar, sit_fundo_classe varchar, sit_fundo varchar, tp_classificacao varchar,
    tp_classificacao_anbima varchar, tp_condominio varchar, tp_publico_alvo varchar,
    fl_exclusivo boolean, cnpj_administrador varchar, nm_administrador varchar,
    cpf_cnpj_gestor varchar, nm_gestor varchar, dt_registro date,
    fl_informa_recente boolean not null default false, dt_valido_de date,
    dt_valido_ate date, fl_versao_atual boolean
);
create table marts.fct_informe_diario (
    sk_fundo varchar, sk_data date, cnpj_fundo_classe varchar, id_subclasse varchar,
    vl_total decimal(18, 2), vl_quota decimal(27, 12), vl_patrim_liq decimal(18, 2),
    vl_captc_dia decimal(18, 2), vl_resg_dia decimal(18, 2),
    vl_captc_liquida_dia decimal(18, 2), nr_cotst integer, dt_mes_competencia date,
    _loaded_at timestamp
);
create table marts.fct_captacao_mensal (
    sk_fundo varchar, sk_mes date, cnpj_fundo_classe varchar, vl_captc_mes decimal(18, 2),
    vl_resg_mes decimal(18, 2), vl_captc_liquida_mes decimal(18, 2),
    vl_patrim_liq_fim_mes decimal(18, 2), nr_cotst_fim_mes integer, dt_ultimo_informe date,
    nr_dias_informados integer
);
"""

MARTS_ROWS = f"""
insert into marts.dim_fundo values
    ('sk1', '{CNPJ_CLASSE}', 'CLASSE', '10', '1', '{CNPJ_FUNDO}', 'CLASSE TESTE', 'FUNDO TESTE',
     'FIF', 'Classes de Cotas', 'EM FUNCIONAMENTO NORMAL', 'EM FUNCIONAMENTO NORMAL', 'Renda Fixa',
     null, 'ABERTO', 'GERAL', false, '{CNPJ_FUNDO}', 'ADMINISTRADORA TESTE', null, null,
     '2020-01-02', true, '1900-01-01', null, true);
insert into marts.fct_informe_diario values
    ('sk1', '2026-08-31', '{CNPJ_CLASSE}', null, 100, 1.5, 100, 10, 2, 8, 3, '2026-08-01',
     '2026-09-01 00:00:00'),
    ('sk1', '2026-09-01', '{CNPJ_CLASSE}', null, 110, 1.6, 110, 5, 0, 5, 3, '2026-09-01',
     '2026-10-01 00:00:00');
insert into marts.fct_captacao_mensal values
    ('sk1', '2026-09-01', '{CNPJ_CLASSE}', 5, 0, 5, 110, 3, '2026-09-01', 1);
"""


def build_warehouse(path: Path, *, with_rows: bool = True) -> Path:
    con = duckdb.connect(str(path))
    try:
        con.execute(MARTS_DDL)
        if with_rows:
            con.execute(MARTS_ROWS)
    finally:
        con.close()
    return path


@pytest.fixture
def warehouse(tmp_path: Path) -> Path:
    return build_warehouse(tmp_path / "warehouse.duckdb")


@pytest.fixture
def settings(warehouse: Path) -> Settings:
    return Settings(duckdb_path=warehouse, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
