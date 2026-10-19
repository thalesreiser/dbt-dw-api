"""Unit tests for the pure helpers of the RF-01 loader."""

import urllib.error
from datetime import date
from pathlib import Path

import pytest

from fundos_api import ingestion as ing


@pytest.mark.parametrize("value", ["2026-09", "2000-01", "2099-12"])
def test_parse_competencia_valid(value: str) -> None:
    year, month = ing.parse_competencia(value)
    assert ing.format_competencia(year, month) == value


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "202609", "2026-9", "1999-12", "abcd-ef"])
def test_parse_competencia_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        ing.parse_competencia(value)


def test_shift_and_previous_competencia() -> None:
    assert ing.shift_competencia("2026-01", -1) == "2025-12"
    assert ing.shift_competencia("2025-12", 1) == "2026-01"
    assert ing.previous_competencia(date(2026, 10, 16)) == "2026-09"
    assert ing.previous_competencia(date(2026, 1, 1)) == "2025-12"


def test_competencia_range() -> None:
    assert ing.competencia_range("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]
    assert ing.competencia_range("2026-02", 1) == ["2026-02"]
    with pytest.raises(ValueError):
        ing.competencia_range("2026-02", 0)


def test_urls() -> None:
    assert ing.informe_diario_url("2026-09") == (
        "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202609.zip"
    )
    assert ing.informe_diario_url("2026-09", "http://localhost:1/") == (
        "http://localhost:1/DOC/INF_DIARIO/DADOS/inf_diario_fi_202609.zip"
    )
    assert ing.registro_url() == (
        "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
    )


def test_normalize_informe_columns_maps_pre_resolution_175_names() -> None:
    mapping = ing.normalize_informe_columns(["TP_FUNDO", "CNPJ_FUNDO", "DT_COMPTC"])
    assert mapping == {
        "TP_FUNDO": "TP_FUNDO_CLASSE",
        "CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE",
        "DT_COMPTC": "DT_COMPTC",
    }


def test_sql_quoting() -> None:
    assert ing.quote_identifier('a"b') == '"a""b"'
    assert ing.sql_literal("o'k") == "'o''k'"
    assert ing.qualified("informe_diario") == "raw.informe_diario"
    with pytest.raises(ValueError):
        ing.qualified("x; drop table y")


def test_parse_args_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    config = ing.parse_args([], today=date(2026, 10, 16))
    assert config.source == "cvm"
    assert config.competencias == ("2026-09",)
    assert config.duckdb_path == Path("data/warehouse.duckdb")
    assert config.base_url == ing.CVM_BASE_URL


def test_parse_args_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKDB_PATH", "x/env.duckdb")
    config = ing.parse_args(["--competencia", "2026-02", "--competencias", "2"])
    assert config.competencias == ("2026-01", "2026-02")
    assert config.duckdb_path == Path("x/env.duckdb")


def test_parse_args_parquet_loads_all_months_by_default() -> None:
    config = ing.parse_args(["--source", "p1-parquet", "--path", "p1/gold"])
    assert config.competencias == ()
    assert config.path == Path("p1/gold")


@pytest.mark.parametrize(
    "argv",
    [
        ["--competencia", "2026-13"],
        ["--competencias", "0"],
        ["--retries", "0"],
        ["--source", "p1-parquet"],
        ["--source", "s3"],
    ],
)
def test_parse_args_rejects_invalid(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        ing.parse_args(argv)


def test_download_retries_then_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def failing_urlopen(*_args: object, **_kwargs: object) -> None:
        calls.append("x")
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr(ing.urllib.request, "urlopen", failing_urlopen)
    sleeps: list[float] = []
    with pytest.raises(urllib.error.URLError):
        ing.download("http://x/y.zip", tmp_path / "y.zip", retries=3, sleep=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("inf_diario_fi_202609.csv", "inf_diario_fi_202609.csv"),
        ("dados/registro_fundo.csv", "registro_fundo.csv"),
        ("../../evil.csv", "evil.csv"),
        ("/tmp/evil.csv", "evil.csv"),
        ("..\..\evil.csv", "evil.csv"),
    ],
)
def test_local_member_name_keeps_only_the_file_name(member: str, expected: str) -> None:
    assert ing.local_member_name(member) == expected


@pytest.mark.parametrize("member", ["", "..", "dados/..", "C:evil.csv"])
def test_local_member_name_rejects_unsafe_names(member: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        ing.local_member_name(member)
