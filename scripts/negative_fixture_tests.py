"""Network-free negative suite (RF-05, task 4.3): invalid data fails exactly the expected tests.

Runs on small synthetic seeds (``dbt/seeds/negative/*.csv``), never on the real warehouse, so it
needs no CVM download (only ``dbt deps``):

1. load the seeds once (``dbt seed --vars '{negative_fixture: true}'``) into a template DuckDB
   file in a temporary directory;
2. for the clean case and every negative case, on a fresh copy of the template:
   - copy the clean seed rows, plus the rows tagged with the case (``negative_case``), into the
     ``raw`` tables the sources read (every column as VARCHAR, like the loader);
   - build every model and the snapshot (``dbt build`` without tests);
   - for the cases that cannot come from raw data (RN-01, orphan fact key, SCD2 overlap), tamper
     the built tables with SQL and rebuild what depends on them;
   - run every test with ``--store-failures`` and compare the failing tests and their failing
     row counts with the expected ones (case -> {test: rows});
3. the clean case must have no failing test, and each negative case exactly its expected ones;
4. discard the temporary directory.

Warnings (``severity: warn``) are reported by dbt but are not failures here. Run from the
repository root after ``make deps``.

Usage: python scripts/negative_fixture_tests.py [--case NAME ...]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]
FIXTURE_VARS = "{negative_fixture: true}"
FIXTURE_SCHEMA = "negative_fixture"
# Seed -> raw table read by the source cvm.<table>.
RAW_TABLES = {
    "neg_informe_diario": "informe_diario",
    "neg_cadastro_fundos": "cadastro_fundos",
    "neg_cadastro_classes": "cadastro_classes",
}
CLASSE_A1 = "11222333000181"


@dataclass
class Case:
    description: str
    expected: dict[str, int]
    # SQL run after the build (tampering), then the models to rebuild.
    tamper: list[str] = field(default_factory=list)
    rebuild: str | None = None


# Long dbt test names (generated from the test arguments) exceed the line length.
SRC_UNIQUE = "dbt_utils_source_unique_combination_of_columns_cvm_informe_diario_CNPJ_FUNDO_CLASSE__ID_SUBCLASSE__DT_COMPTC"  # noqa: E501
STG_UNIQUE = "dbt_utils_unique_combination_of_columns_stg_cvm__informe_diario_cnpj_fundo_classe__id_subclasse__dt_competencia"  # noqa: E501
FCT_UNIQUE = "dbt_utils_unique_combination_of_columns_fct_informe_diario_cnpj_fundo_classe__id_subclasse__sk_data"  # noqa: E501
SRC_FK_FUNDO = "source_relationships_cvm_cadastro_classes_ID_Registro_Fundo__ID_Registro_Fundo__source_cvm_cadastro_fundos_"  # noqa: E501
STG_FK_FUNDO = "relationships_stg_cvm__cadastro_classes_id_registro_fundo__id_registro_fundo__ref_stg_cvm__cadastro_fundos_"  # noqa: E501
STG_NOT_AFTER_LOAD = "dbt_utils_expression_is_true_stg_cvm__informe_diario_dt_competencia___cast__loaded_at_as_date_"  # noqa: E501
STG_IN_MONTH = "dbt_utils_expression_is_true_stg_cvm__informe_diario_date_trunc_month_dt_competencia_dt_mes_competencia"  # noqa: E501
FCT_IN_MONTH = "dbt_utils_expression_is_true_fct_informe_diario_dt_mes_competencia_date_trunc_month_sk_data_"  # noqa: E501
FCT_MES_NET = "dbt_utils_expression_is_true_fct_captacao_mensal_vl_captc_liquida_mes_vl_captc_mes_vl_resg_mes"  # noqa: E501

CASES: dict[str, Case] = {
    "clean": Case("clean seeds only: every test passes", {}),
    "null_key": Case(
        "null key: daily report row without CNPJ",
        {
            "source_not_null_cvm_informe_diario_CNPJ_FUNDO_CLASSE": 1,
            "not_null_stg_cvm__informe_diario_cnpj_fundo_classe": 1,
            "not_null_fct_informe_diario_cnpj_fundo_classe": 1,
            "not_null_fct_captacao_mensal_cnpj_fundo_classe": 1,
            # A null CNPJ also breaks the joins on the key of the monthly reconciliations.
            "assert_rn01_monthly_net_inflow_matches_staging": 2,
            "assert_fct_captacao_mensal_reconciles_daily": 2,
        },
    ),
    "duplicate_key": Case(
        "duplicate key: daily report row repeated (same class and date)",
        {SRC_UNIQUE: 1, STG_UNIQUE: 1, FCT_UNIQUE: 1},
    ),
    "orphan_fk": Case(
        "orphan key in the registry: class whose fund registry id does not exist",
        {SRC_FK_FUNDO: 1, STG_FK_FUNDO: 1},
    ),
    "orphan_fact_fk": Case(
        "orphan key fact -> dim: daily fact row pointing to no dim_fundo version",
        {"relationships_fct_informe_diario_sk_fundo__sk_fundo__ref_dim_fundo_": 1},
        tamper=[
            "update marts.fct_informe_diario set sk_fundo = 'no-such-version'"
            f" where cnpj_fundo_classe = '{CLASSE_A1}' and sk_data = date '2026-09-02'"
        ],
    ),
    "rn01_net_inflow": Case(
        "RN-01: net inflow is no longer inflows - redemptions (one daily, one monthly row)",
        {
            "rn01_fct_informe_diario_net_inflow": 1,
            "rn01_fct_captacao_mensal_net_inflow": 1,
            FCT_MES_NET: 1,
            "assert_rn01_monthly_net_inflow_matches_staging": 1,
            "assert_fct_captacao_mensal_reconciles_daily": 2,
        },
        tamper=[
            "update marts.fct_informe_diario set vl_captc_liquida_dia = vl_captc_liquida_dia + 1"
            f" where cnpj_fundo_classe = '{CLASSE_A1}' and sk_data = date '2026-09-01'",
            "update marts.fct_captacao_mensal set vl_captc_liquida_mes = vl_captc_liquida_mes + 1"
            f" where cnpj_fundo_classe = '{CLASSE_A1}' and sk_mes = date '2026-08-01'",
        ],
    ),
    "rn02_negative_flow": Case(
        "RN-02: negative daily inflow",
        {
            "dbt_utils_accepted_range_stg_cvm__informe_diario_vl_captc_dia__0": 1,
            "rn02_stg_informe_diario_flows_not_negative": 1,
            "rn02_fct_informe_diario_flows_not_negative": 1,
            "rn02_fct_captacao_mensal_flows_not_negative": 1,
        },
    ),
    "rn02_future_date": Case(
        "RN-02: report dated in the future (2999-12-15, in its own reference month)",
        {
            "rn02_stg_informe_diario_no_future_date": 1,
            "rn02_fct_informe_diario_no_future_date": 1,
            "rn02_fct_captacao_mensal_no_future_date": 1,
            STG_NOT_AFTER_LOAD: 1,
            # The calendar ends with the current year, so the date is also an orphan.
            "relationships_fct_informe_diario_sk_data__sk_data__ref_dim_data_": 1,
            "relationships_fct_captacao_mensal_sk_mes__sk_data__ref_dim_data_": 1,
        },
    ),
    "rn02_outside_month": Case(
        "RN-02: report date (2026-08-28) outside its reference month (2026-09)",
        {"rn02_stg_informe_diario_date_in_reference_month": 1, STG_IN_MONTH: 1, FCT_IN_MONTH: 1},
    ),
    "scd2_two_current": Case(
        "SCD2: a second open version of the same CNPJ (overlap, two current versions)",
        {
            "assert_dim_fundo_one_current_version": 1,
            "assert_dim_fundo_versions_contiguous": 2,
            "unique_dim_fundo_cnpj_fundo_classe": 1,
        },
        tamper=[
            "insert into snapshots.snp_cvm__fundo_classe select * replace ("
            " dbt_scd_id || '-dup' as dbt_scd_id,"
            " dbt_valid_from - interval 30 day as dbt_valid_from)"
            f" from snapshots.snp_cvm__fundo_classe where cnpj_fundo_classe = '{CLASSE_A1}'"
        ],
        rebuild="dim_fundo",
    ),
}


def dbt(args: list[str], env: dict[str, str], check: bool = True) -> int:
    exe = shutil.which("dbt")
    if exe is None:
        sys.exit("dbt not found on PATH")
    print("$ dbt " + " ".join(args), flush=True)
    proc = subprocess.run(
        [exe, *args, *DBT_ARGS], cwd=ROOT, env=env, check=False, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-4000:])
        sys.exit(f"dbt {args[0]} failed")
    return proc.returncode


def load_raw(db: Path, case: str) -> None:
    """Create the raw tables from the clean seed rows plus the rows of the case."""
    with duckdb.connect(str(db)) as con:
        con.execute("create schema if not exists raw")
        for seed, table in RAW_TABLES.items():
            cols = [
                r[0]
                for r in con.execute(
                    "select column_name from information_schema.columns"
                    " where table_schema = ? and table_name = ? order by ordinal_position",
                    [FIXTURE_SCHEMA, seed],
                ).fetchall()
                if r[0] != "negative_case"
            ]
            select = ", ".join(f'cast("{c}" as varchar) as "{c}"' for c in cols)
            con.execute(
                f"create or replace table raw.{table} as select {select},"
                " current_timestamp as _loaded_at"
                f" from {FIXTURE_SCHEMA}.{seed}"
                " where negative_case is null or negative_case = ?",
                [case],
            )


def failing_tests(env: dict[str, str], target: Path) -> dict[str, int]:
    """Run every test and return {test name: failing rows} for the failed (or errored) ones."""
    dbt(["test", "--store-failures", "--target-path", str(target)], env, check=False)
    results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))["results"]
    statuses = [r["status"] for r in results]
    print("  tests: " + ", ".join(f"{s} {statuses.count(s)}" for s in sorted(set(statuses))))
    return {
        r["unique_id"].split(".")[2]: int(r.get("failures") or 0)
        for r in results
        if r["status"] in ("fail", "error")
    }


def run_case(name: str, case: Case, template: Path, workdir: Path) -> dict[str, int]:
    db = workdir / f"{name}.duckdb"
    shutil.copyfile(template, db)
    env = {**os.environ, "DUCKDB_PATH": str(db)}
    load_raw(db, name)
    dbt(["build", "--exclude", "resource_type:test", "resource_type:seed"], env)
    if case.tamper:
        with duckdb.connect(str(db)) as con:
            for sql in case.tamper:
                con.execute(sql)
        if case.rebuild:
            dbt(["run", "--select", case.rebuild], env)
    return failing_tests(env, workdir / f"target-{name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", action="append", choices=sorted(CASES), help="run only these")
    args = parser.parse_args()
    selected = args.case or list(CASES)

    workdir = Path(tempfile.mkdtemp(prefix="negative-fixture-"))
    try:
        template = workdir / "template.duckdb"
        env = {**os.environ, "DUCKDB_PATH": str(template)}
        dbt(["seed", "--vars", FIXTURE_VARS, "--target-path", str(workdir / "target-seed")], env)
        observed = {name: run_case(name, CASES[name], template, workdir) for name in selected}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    ok = True
    print("\ncase | test | expected rows | failing rows")
    for name in selected:
        expected, got = CASES[name].expected, observed[name]
        print(f"## {name}: {CASES[name].description}")
        for test in sorted(set(expected) | set(got)):
            match = expected.get(test) == got.get(test)
            ok &= match
            flag = "OK  " if match else "DIFF"
            print(f"{flag} {name} | {test} | {expected.get(test)} | {got.get(test)}")
        if not expected and not got:
            print(f"OK   {name} | (no failing test)")
    if not ok:
        sys.exit("negative fixture suite failed: failing tests differ from the expected ones")
    print(f"\nnegative fixture suite passed: {len(selected)} cases, failing tests as expected")


if __name__ == "__main__":
    main()
