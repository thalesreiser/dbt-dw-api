"""Integration tests of the RF-01 loader: tiny synthetic CVM files, no internet."""

from __future__ import annotations

import functools
import http.server
import threading
import urllib.error
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from fundos_api import ingestion as ing

INFORME_HEADER = (
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;"
    "VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST"
)
REGISTRO_FUNDO = (
    "ID_Registro_Fundo;CNPJ_Fundo;Denominacao_Social;Situacao\n"
    "1;00017024000153;FUNDO AÇÕES;Em Funcionamento Normal\n"
    "2;11111111000111;FUNDO RENDA FIXA;Cancelado\n"
)
REGISTRO_CLASSE = (
    "ID_Registro_Fundo;ID_Registro_Classe;CNPJ_Classe;Denominacao_Social\n"
    "1;10;00017024000153;CLASSE ÚNICA\n"
)


def informe_csv(month: str, days: int, old_layout: bool = False) -> str:
    if old_layout:  # layout before CVM Resolution 175: CNPJ_FUNDO, TP_FUNDO, no subclass
        header = INFORME_HEADER.replace("_CLASSE", "").replace("ID_SUBCLASSE;", "")
        row = "FI;00.017.024/0001-53;{day};1.0;2.0;3.0;0;0;1"
    else:
        header = INFORME_HEADER
        row = "CLASSES - FIF;00.017.024/0001-53;;{day};1.0;2.0;3.0;0;0;1"
    lines = [header] + [row.format(day=f"{month}-{d:02d}") for d in range(1, days + 1)]
    return "\n".join(lines) + "\n"


def write_zip(path: Path, members: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text.encode("latin-1"))


@pytest.fixture()
def cvm_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Serve a fake CVM tree (DOC/INF_DIARIO/DADOS + CAD/DADOS) from a local HTTP server."""
    root = tmp_path / "www"
    daily = root / "DOC" / "INF_DIARIO" / "DADOS"
    write_zip(
        daily / "inf_diario_fi_202608.zip", {"inf_diario_fi_202608.csv": informe_csv("2026-08", 3)}
    )
    write_zip(
        daily / "inf_diario_fi_202609.zip", {"inf_diario_fi_202609.csv": informe_csv("2026-09", 2)}
    )
    write_zip(
        daily / "inf_diario_fi_202001.zip",
        {"inf_diario_fi_202001.csv": informe_csv("2020-01", 4, old_layout=True)},
    )
    write_zip(
        root / "CAD" / "DADOS" / "registro_fundo_classe.zip",
        {
            "registro_fundo.csv": REGISTRO_FUNDO,
            "registro_classe.csv": REGISTRO_CLASSE,
            "registro_subclasse.csv": "ID_Registro_Classe;ID_Subclasse\n",
        },
    )

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

    handler = functools.partial(QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path / "wh.duckdb"
    finally:
        server.shutdown()
        server.server_close()


def counts_by_month(db: Path) -> dict[str, int]:
    with duckdb.connect(str(db), read_only=True) as con:
        rows = con.execute(
            "SELECT competencia, count(*) FROM raw.informe_diario GROUP BY 1 ORDER BY 1"
        ).fetchall()
    return {str(month): int(n) for month, n in rows}


def run_cvm(base_url: str, db: Path, *extra: str) -> int:
    return ing.main(["--duckdb", str(db), "--base-url", base_url, "--retries", "1", *extra])


def test_load_cvm_rows_and_idempotency(cvm_server: tuple[str, Path]) -> None:
    base_url, db = cvm_server
    assert run_cvm(base_url, db, "--competencia", "2026-09", "--competencias", "2") == 0
    assert counts_by_month(db) == {"2026-08": 3, "2026-09": 2}

    # Reloading a month replaces it: no duplicates.
    assert run_cvm(base_url, db, "--competencia", "2026-09") == 0
    assert run_cvm(base_url, db, "--competencia", "2026-09") == 0
    assert counts_by_month(db) == {"2026-08": 3, "2026-09": 2}

    with duckdb.connect(str(db), read_only=True) as con:
        assert ing.row_counts(con) == {
            "informe_diario": 5,
            "cadastro_fundos": 2,
            "cadastro_classes": 1,
        }
        name = con.execute(
            "SELECT Denominacao_Social FROM raw.cadastro_fundos WHERE ID_Registro_Fundo = '1'"
        ).fetchone()
        assert name == ("FUNDO AÇÕES",)  # latin-1 decoded correctly
        meta = con.execute(
            "SELECT DISTINCT _source, typeof(_loaded_at) FROM raw.informe_diario"
        ).fetchall()
        assert meta == [("cvm", "TIMESTAMP")]


def test_load_cvm_old_layout_is_normalized(cvm_server: tuple[str, Path]) -> None:
    base_url, db = cvm_server
    run_cvm(base_url, db, "--competencia", "2026-09")
    run_cvm(base_url, db, "--competencia", "2020-01")
    assert counts_by_month(db) == {"2020-01": 4, "2026-09": 2}
    with duckdb.connect(str(db), read_only=True) as con:
        missing = con.execute(
            "SELECT count(*) FROM raw.informe_diario WHERE CNPJ_FUNDO_CLASSE IS NULL"
        ).fetchone()
        assert missing == (0,)


def test_load_cvm_missing_month_fails(cvm_server: tuple[str, Path]) -> None:
    base_url, db = cvm_server
    with pytest.raises(urllib.error.HTTPError):
        run_cvm(base_url, db, "--competencia", "2026-12")


def write_parquet(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({sql}) TO '{path.as_posix()}' (FORMAT PARQUET)")


def test_load_p1_parquet(tmp_path: Path) -> None:
    base = tmp_path / "p1"
    with duckdb.connect() as con:
        write_parquet(
            con,
            "SELECT 'CLASSES - FIF' AS TP_FUNDO_CLASSE, '00.017.024/0001-53' AS CNPJ_FUNDO_CLASSE, "
            "NULL::VARCHAR AS ID_SUBCLASSE, d::DATE AS DT_COMPTC, 1.5::DOUBLE AS VL_QUOTA "
            "FROM range(DATE '2026-08-30', DATE '2026-09-03', INTERVAL 1 DAY) t(d)",
            base / "informe_diario" / "part-0.parquet",
        )
        write_parquet(
            con,
            "SELECT 1 AS ID_Registro_Fundo, '00017024000153' AS CNPJ_Fundo",
            base / "cadastro_fundos" / "part-0.parquet",
        )
        write_parquet(
            con,
            "SELECT 1 AS ID_Registro_Fundo, 10 AS ID_Registro_Classe, "
            "'00017024000153' AS CNPJ_Classe",
            base / "cadastro_classes" / "part-0.parquet",
        )

    db = tmp_path / "wh.duckdb"
    argv = ["--source", "p1-parquet", "--path", str(base), "--duckdb", str(db)]
    assert ing.main(argv) == 0
    assert ing.main(argv) == 0  # idempotent
    assert counts_by_month(db) == {"2026-08": 2, "2026-09": 2}

    # Filtering by reference month only replaces that month.
    assert ing.main([*argv, "--competencia", "2026-09"]) == 0
    assert counts_by_month(db) == {"2026-08": 2, "2026-09": 2}

    with duckdb.connect(str(db), read_only=True) as con:
        assert ing.row_counts(con) == {
            "informe_diario": 4,
            "cadastro_fundos": 1,
            "cadastro_classes": 1,
        }
        types = dict(
            con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'informe_diario'"
            ).fetchall()
        )
        assert types["DT_COMPTC"] == "VARCHAR"
        assert types["_loaded_at"] == "TIMESTAMP"
        source = con.execute("SELECT DISTINCT _source FROM raw.cadastro_classes").fetchall()
        assert source == [("p1-parquet",)]


def test_run_uses_naive_utc_timestamp(tmp_path: Path) -> None:
    base = tmp_path / "p1"
    with duckdb.connect() as con:
        for table in ("informe_diario", "cadastro_fundos", "cadastro_classes"):
            write_parquet(
                con,
                "SELECT '00.017.024/0001-53' AS CNPJ_FUNDO_CLASSE, DATE '2026-09-01' AS DT_COMPTC",
                base / table / "part-0.parquet",
            )
    config = ing.parse_args(
        ["--source", "p1-parquet", "--path", str(base), "--duckdb", str(tmp_path / "w.duckdb")]
    )
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    ing.run(config, now=now)
    with duckdb.connect(str(tmp_path / "w.duckdb"), read_only=True) as con:
        loaded = con.execute("SELECT max(_loaded_at) FROM raw.informe_diario").fetchone()
    assert loaded == (datetime(2026, 10, 1, 12, 0),)
