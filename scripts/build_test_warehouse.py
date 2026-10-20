"""Build the test warehouse of the API integration tests (task 5.6) from synthetic raw data.

Network-free once ``dbt deps`` has run (the script runs it when ``dbt/dbt_packages`` is missing):

1. load the CSV files in ``tests/fixtures/warehouse/`` (synthetic rows in the layout of the three
   CVM sources; every CNPJ synthetic, with valid check digits; no natural persons) into the
   ``raw`` tables the sources read, every column as VARCHAR like the loader, in a new DuckDB file;
2. run the real dbt project on it: ``dbt build`` (seeds, staging, snapshot, marts and every
   test), failing if any model or test fails.

The result has the marts the API reads (``dim_fundo``, ``fct_informe_diario``,
``fct_captacao_mensal``) built by the actual models, so the integration tests exercise the API
over the same SQL as production. The real warehouse (``data/warehouse.duckdb``) is never touched.

Usage: python scripts/build_test_warehouse.py [--output PATH]
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "warehouse"
DBT_ARGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]
RAW_TABLES = ("informe_diario", "cadastro_fundos", "cadastro_classes")


def _dbt(args: list[str], env: dict[str, str]) -> None:
    exe = shutil.which("dbt")
    if exe is None:
        raise RuntimeError("dbt not found on PATH")
    proc = subprocess.run(
        [exe, *args, *DBT_ARGS], cwd=ROOT, env=env, check=False, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"dbt {args[0]} failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")


def load_raw(db: Path, fixtures: Path = FIXTURES) -> None:
    """Create the ``raw`` tables from the fixture CSV files (all VARCHAR, plus ``_loaded_at``).

    Read with the ``csv`` module (empty field = NULL) rather than DuckDB's sniffer, so the
    tiny files never depend on dialect detection.
    """
    with duckdb.connect(str(db)) as con:
        con.execute("create schema if not exists raw")
        for table in RAW_TABLES:
            with (fixtures / f"{table}.csv").open(encoding="utf-8", newline="") as fh:
                header, *rows = list(csv.reader(fh))
            cols = ", ".join(f'"{c}" varchar' for c in header)
            con.execute(f"create or replace table raw.{table} ({cols})")
            marks = ", ".join("?" for _ in header)
            con.executemany(
                f"insert into raw.{table} values ({marks})",
                [[v if v != "" else None for v in row] for row in rows],
            )
            con.execute(
                f"alter table raw.{table} add column _loaded_at timestamp"
                " default current_timestamp"
            )
            con.execute(f"update raw.{table} set _loaded_at = current_timestamp")


def build_test_warehouse(db: Path, fixtures: Path = FIXTURES) -> Path:
    """Build a fresh test warehouse at ``db`` with the real dbt project; return its path."""
    db = db.resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    load_raw(db, fixtures)
    env = {**os.environ, "DUCKDB_PATH": str(db)}
    if not (ROOT / "dbt" / "dbt_packages").is_dir():
        _dbt(["deps"], env)
    with tempfile.TemporaryDirectory(prefix="test-warehouse-") as target:
        _dbt(["build", "--target-path", target], env)
    return db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data" / "test_warehouse.duckdb", help="DuckDB file"
    )
    args = parser.parse_args()
    try:
        path = build_test_warehouse(args.output)
    except RuntimeError as exc:
        sys.exit(str(exc))
    print(f"test warehouse built: {path}")


if __name__ == "__main__":
    main()
