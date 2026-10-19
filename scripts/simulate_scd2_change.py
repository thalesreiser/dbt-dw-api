"""Simulate a registry change and prove the SCD2 history of dim_fundo (RF-04, task 3.4).

Works on a temporary copy of the DuckDB file, so the warehouse and its snapshot history are
never touched:

1. copy the warehouse to a temporary directory and point dbt at it (DUCKDB_PATH);
2. build the unified registry view and run ``dbt snapshot`` (first version of every CNPJ),
   then move that version's timestamps back one day: dim_fundo keeps the last version of each
   day, so a change on the same day as the first snapshot would collapse into one version;
3. change the legal name of one class in ``raw.cadastro_classes``;
4. run ``dbt snapshot`` again and build ``dim_fundo`` with its tests;
5. assert that the class now has two versions with contiguous validity:
   [1900-01-01, today) with the old name, then [today, open) with the new one.

Requires a warehouse already loaded (``make load``). Run from the repository root.

Usage: python scripts/simulate_scd2_change.py [--cnpj CNPJ_CLASSE]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]
SUFFIX = " [SCD2 TEST]"


def run_dbt(args: list[str], env: dict[str, str]) -> None:
    dbt = shutil.which("dbt")
    if dbt is None:
        sys.exit("dbt not found on PATH")
    print("$ dbt " + " ".join(args), flush=True)
    subprocess.run([dbt, *args, *DBT_ARGS], cwd=ROOT, env=env, check=True)


def pick_class(con: duckdb.DuckDBPyConnection, cnpj: str | None) -> tuple[str, str, str]:
    """Return (cnpj_fundo_classe, id_registro_classe, nm_denominacao_social) of a class."""
    sql = """
        select cnpj_fundo_classe, id_registro_classe, nm_denominacao_social
        from snapshots.snp_cvm__fundo_classe
        where dbt_valid_to is null and tp_registro = 'CLASSE'
          and (? is null or cnpj_fundo_classe = ?)
        order by cnpj_fundo_classe
        limit 1
    """
    row = con.execute(sql, [cnpj, cnpj]).fetchone()
    if row is None:
        sys.exit(f"no current CLASSE row in the snapshot (cnpj={cnpj})")
    return str(row[0]), str(row[1]), str(row[2])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cnpj", help="class CNPJ to change (default: the first current one)")
    args = parser.parse_args()

    source = ROOT / os.environ.get("DUCKDB_PATH", "data/warehouse.duckdb")
    if not source.exists():
        sys.exit(f"warehouse not found: {source} (run `make load` first)")

    workdir = Path(tempfile.mkdtemp(prefix="scd2-sim-"))
    try:
        db = workdir / "warehouse.duckdb"
        shutil.copyfile(source, db)
        env = {**os.environ, "DUCKDB_PATH": str(db)}

        run_dbt(["run", "--select", "+int_fundo_classe__unificado"], env)
        run_dbt(["snapshot", "--select", "snp_cvm__fundo_classe"], env)

        with duckdb.connect(str(db)) as con:
            cnpj, id_classe, old_name = pick_class(con, args.cnpj)
            con.execute(
                "update snapshots.snp_cvm__fundo_classe set"
                " dbt_valid_from = dbt_valid_from - interval 1 day,"
                " dbt_updated_at = dbt_updated_at - interval 1 day"
                " where cnpj_fundo_classe = ?",
                [cnpj],
            )
            new_name = old_name + SUFFIX
            con.execute(
                "update raw.cadastro_classes set Denominacao_Social = Denominacao_Social || ?"
                " where ID_Registro_Classe = ?",
                [SUFFIX, id_classe],
            )
        print(f"changed {cnpj} (class id {id_classe}): {old_name!r} -> {new_name!r}")

        run_dbt(["snapshot", "--select", "snp_cvm__fundo_classe"], env)
        run_dbt(["build", "--select", "dim_fundo"], env)

        with duckdb.connect(str(db), read_only=True) as con:
            rows = con.execute(
                "select sk_fundo, nm_denominacao_social, dt_valido_de, dt_valido_ate,"
                " fl_versao_atual from marts.dim_fundo where cnpj_fundo_classe = ?"
                " order by dt_valido_de",
                [cnpj],
            ).fetchall()
            today = con.execute("select current_date").fetchone()[0]  # type: ignore[index]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("sk_fundo | nm_denominacao_social | dt_valido_de | dt_valido_ate | fl_versao_atual")
    for row in rows:
        print(" | ".join(str(value) for value in row))

    if len(rows) != 2:
        sys.exit(f"expected 2 versions of {cnpj}, got {len(rows)}")
    (_, name_1, from_1, to_1, current_1), (_, name_2, from_2, to_2, current_2) = rows
    checks = {
        "old version keeps the old name": name_1 == old_name,
        "new version has the new name": name_2 == new_name,
        "first version starts at 1900-01-01": from_1 == date(1900, 1, 1),
        "old version ends where the new one starts": to_1 is not None and to_1 == from_2,
        "new version starts today": from_2 == today,
        "new version is open": to_2 is None,
        "only the new version is current": (current_1, current_2) == (False, True),
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not all(checks.values()):
        sys.exit("SCD2 simulation failed")
    print(f"SCD2 simulation passed: 2 versions of {cnpj}")


if __name__ == "__main__":
    main()
