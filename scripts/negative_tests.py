"""Negative proof of the RN-01 / RN-02 tests (RF-05, task 4.1).

Works on a temporary copy of the DuckDB file, so the warehouse is never touched:

1. copy the warehouse to a temporary directory and point dbt at it (DUCKDB_PATH);
2. run the rule tests on the copy and assert they all PASS (baseline);
3. inject invalid data:
   - RN-02 (amounts): one raw daily report row gets a negative inflow (``CAPTC_DIA``);
   - RN-02 (dates): one raw daily report row is duplicated with a report date in the future,
     outside its reference month;
   - rebuild ``stg_cvm__informe_diario`` and everything downstream (the facts);
   - RN-01: one daily fact row and one monthly fact row get a net inflow that is no longer
     inflows - redemptions;
   - RN-02 (types): the monthly net assets column is stored as DOUBLE instead of DECIMAL
     (a column outside RN-01, so the RN-01 tests count only the tampered rows);
4. run the same tests again and assert that every expected test FAILS;
5. discard the copy.

Requires a warehouse with the marts built (``make marts``). Run from the repository root.

Usage: python scripts/negative_tests.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]

# Test name -> the injected row that must make it fail.
EXPECTED_FAILURES = {
    # RN-01: net inflows = inflows - redemptions.
    "rn01_fct_informe_diario_net_inflow": "daily fact row with a tampered net inflow",
    "rn01_fct_captacao_mensal_net_inflow": "monthly fact row with a tampered net inflow",
    "assert_rn01_monthly_net_inflow_matches_staging": "monthly net inflow differs from staging",
    "assert_fct_captacao_mensal_reconciles_daily": "monthly fact no longer matches the daily one",
    # RN-02: amounts in BRL as non-negative decimals.
    "rn02_stg_informe_diario_flows_not_negative": "raw row with a negative inflow",
    "rn02_fct_informe_diario_flows_not_negative": "raw row with a negative inflow",
    "rn02_fct_captacao_mensal_money_is_decimal": "vl_patrim_liq_fim_mes stored as DOUBLE",
    # RN-02: dates within the reference month and never in the future.
    "rn02_stg_informe_diario_no_future_date": "raw row dated in the future",
    "rn02_stg_informe_diario_date_in_reference_month": "raw row outside its reference month",
    "rn02_fct_informe_diario_no_future_date": "raw row dated in the future",
    "rn02_fct_captacao_mensal_no_future_date": "raw row dated in the future",
}


def dbt(args: list[str], env: dict[str, str], check: bool = True) -> int:
    exe = shutil.which("dbt")
    if exe is None:
        sys.exit("dbt not found on PATH")
    print("$ dbt " + " ".join(args), flush=True)
    return subprocess.run([exe, *args, *DBT_ARGS], cwd=ROOT, env=env, check=check).returncode


def test_statuses(env: dict[str, str], target: Path) -> dict[str, tuple[str, int | None]]:
    """Run the expected tests and return {test name: (status, failing rows)}."""
    dbt(["test", "--select", *EXPECTED_FAILURES, "--target-path", str(target)], env, check=False)
    results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))["results"]
    return {r["unique_id"].split(".")[2]: (r["status"], r.get("failures")) for r in results}


def inject(db: Path) -> None:
    with duckdb.connect(str(db)) as con:
        month = con.execute("select max(competencia) from raw.informe_diario").fetchone()[0]  # type: ignore[index]
        rows = con.execute(
            "select CNPJ_FUNDO_CLASSE, ID_SUBCLASSE, DT_COMPTC from raw.informe_diario"
            " where competencia = ? order by CNPJ_FUNDO_CLASSE, DT_COMPTC limit 2",
            [month],
        ).fetchall()
        (cnpj_neg, sub_neg, dt_neg), (cnpj_fut, sub_fut, dt_fut) = rows
        # RN-02 (amounts): a negative inflow; _loaded_at moves so the incremental fact reloads.
        con.execute(
            "update raw.informe_diario set CAPTC_DIA = '-1000.00', _loaded_at = now()"
            " where CNPJ_FUNDO_CLASSE = ? and ID_SUBCLASSE is not distinct from ?"
            " and DT_COMPTC = ?",
            [cnpj_neg, sub_neg, dt_neg],
        )
        # RN-02 (dates): a copy of another row dated tomorrow, outside its reference month.
        con.execute(
            "insert into raw.informe_diario select * replace ("
            " strftime(current_date + 1, '%Y-%m-%d') as DT_COMPTC, now() as _loaded_at)"
            " from raw.informe_diario where CNPJ_FUNDO_CLASSE = ?"
            " and ID_SUBCLASSE is not distinct from ? and DT_COMPTC = ?",
            [cnpj_fut, sub_fut, dt_fut],
        )
    print(f"RN-02: negative inflow in {cnpj_neg} on {dt_neg}; future-dated copy of {cnpj_fut}")

    env = {**os.environ, "DUCKDB_PATH": str(db)}
    dbt(["run", "--select", "stg_cvm__informe_diario+"], env)

    with duckdb.connect(str(db)) as con:
        cnpj_d, sub_d, dt_d = con.execute(
            "select cnpj_fundo_classe, id_subclasse, sk_data from marts.fct_informe_diario"
            " order by all desc limit 1",
        ).fetchone()  # type: ignore[misc]
        # RN-01 (daily): net inflow no longer equals inflows - redemptions.
        con.execute(
            "update marts.fct_informe_diario set vl_captc_liquida_dia = vl_captc_liquida_dia + 1"
            " where cnpj_fundo_classe = ? and id_subclasse is not distinct from ? and sk_data = ?",
            [cnpj_d, sub_d, dt_d],
        )
        cnpj_m, mes_m = con.execute(
            "select cnpj_fundo_classe, sk_mes from marts.fct_captacao_mensal"
            " where cnpj_fundo_classe <> ? order by all desc limit 1",
            [cnpj_d],
        ).fetchone()  # type: ignore[misc]
        # RN-01 (monthly): the same for one class and month.
        con.execute(
            "update marts.fct_captacao_mensal set vl_captc_liquida_mes = vl_captc_liquida_mes + 1"
            " where cnpj_fundo_classe = ? and sk_mes = ?",
            [cnpj_m, mes_m],
        )
        # RN-02 (types): money stored as a float.
        con.execute(
            "create or replace table marts.fct_captacao_mensal as select * replace"
            " (cast(vl_patrim_liq_fim_mes as double) as vl_patrim_liq_fim_mes)"
            " from marts.fct_captacao_mensal"
        )
    print(f"RN-01: tampered daily row {cnpj_d} on {dt_d} and monthly row {cnpj_m} {mes_m}")
    print("RN-02: marts.fct_captacao_mensal.vl_patrim_liq_fim_mes is now DOUBLE")


def main() -> None:
    source = ROOT / os.environ.get("DUCKDB_PATH", "data/warehouse.duckdb")
    if not source.exists():
        sys.exit(f"warehouse not found: {source} (run `make marts` first)")

    workdir = Path(tempfile.mkdtemp(prefix="negative-tests-"))
    try:
        db = workdir / "warehouse.duckdb"
        shutil.copyfile(source, db)
        env = {**os.environ, "DUCKDB_PATH": str(db)}

        baseline = test_statuses(env, workdir / "target-baseline")
        not_passing = {k: v for k, v in baseline.items() if v[0] != "pass"}
        missing = set(EXPECTED_FAILURES) - set(baseline)
        if not_passing or missing:
            sys.exit(f"baseline must pass: not passing {not_passing}, missing {sorted(missing)}")
        print(f"baseline: {len(baseline)} rule tests PASS")

        inject(db)
        after = test_statuses(env, workdir / "target-injected")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    ok = True
    print("test | status | failing rows | injected")
    for name, reason in EXPECTED_FAILURES.items():
        status, failures = after.get(name, ("missing", None))
        ok &= status == "fail"
        print(f"{'OK  ' if status == 'fail' else 'MISS'} {name} | {status} | {failures} | {reason}")
    if not ok:
        sys.exit("negative tests failed: some rule tests did not detect the invalid data")
    print(f"negative tests passed: all {len(EXPECTED_FAILURES)} rule tests failed as expected")


if __name__ == "__main__":
    main()
