"""RNF-01 (6.2): the load test report aggregates locust stats and samples synthetic CNPJs."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import duckdb

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loadtest_report.py"
HEADER = (
    "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,"
    "Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,"
    "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loadtest_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stats(tmp_path: Path, serie_p95: int) -> Path:
    path = tmp_path / "locust_stats.csv"
    path.write_text(
        HEADER + "\n" + f"GET,/v1/fundos/[cnpj]/serie,800,8,40,50,5,900,1000,13.3,0.1,"
        f"40,45,50,60,80,{serie_p95},200,250,400,900,900\n"
        + "GET,/v1/fundos,100,0,60,70,10,300,9000,1.7,0,60,65,70,75,90,120,150,200,300,300,300\n"
        + ",Aggregated,900,8,45,52,5,900,1500,15,0.1,45,50,55,60,85,140,190,240,400,900,900\n"
    )
    return path


def test_report_aggregates_and_target(tmp_path: Path) -> None:
    mod = _load()
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    args = ["report", "--stats", str(_stats(tmp_path, 120)), "--json", str(out_json)]
    rc = mod.main([*args, "--markdown", str(out_md), "--fail-on-miss"])
    assert rc == 0
    summary = json.loads(out_json.read_text())
    assert summary["met"] is True
    serie = summary["endpoints"][0]
    assert serie["name"] == "/v1/fundos/[cnpj]/serie"
    assert (serie["p50_ms"], serie["p95_ms"], serie["p99_ms"]) == (40, 120, 250)
    assert serie["error_rate"] == 0.01 and serie["rps"] == 13.3
    assert "**met**" in out_md.read_text()


def test_report_fails_on_miss(tmp_path: Path) -> None:
    mod = _load()
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    args = ["report", "--stats", str(_stats(tmp_path, 310)), "--json", str(out_json)]
    assert mod.main([*args, "--markdown", str(out_md), "--fail-on-miss"]) == 1
    assert "NOT met" in out_md.read_text()


def test_sample_current_reporting_cnpjs(tmp_path: Path) -> None:
    db = tmp_path / "w.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create schema marts")
        con.execute(
            "create table marts.dim_fundo as select * from (values "
            "('11111111000111', true, true, 'CLASSE'), "
            "('22222222000122', false, true, 'CLASSE'), "
            "('33333333000133', true, false, 'CLASSE'), "
            "('00000000000000', true, true, 'DESCONHECIDO')) "
            "t(cnpj_fundo_classe, fl_versao_atual, fl_informa_recente, tp_registro)"
        )
    out = tmp_path / "cnpjs.txt"
    assert _load().main(["sample", "--db", str(db), "-n", "10", "--out", str(out)]) == 0
    assert out.read_text().split() == ["11111111000111"]
