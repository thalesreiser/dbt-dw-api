"""RF-01 / R-P3-01: load the source tables into the DuckDB ``raw`` schema.

Two pluggable sources feed the same raw tables declared in ``dbt/models/staging/_sources.yml``:

* ``cvm``: direct download of the CVM open data (fallback while P1 is not ready, R-P3-01);
* ``p1-parquet``: Parquet files produced by P1 (aws-fundos-pipeline), read from a path.

Pure helpers (reference month handling, URL building, CLI parsing, column mapping) are kept
separate from the I/O functions (download, transcoding, DuckDB writes) so they are unit-testable.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

import duckdb

logger = logging.getLogger(__name__)

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/FI"
INFORME_DIARIO_PATH = "DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
REGISTRO_PATH = "CAD/DADOS/registro_fundo_classe.zip"
CVM_ENCODING = "latin-1"
CSV_DELIMITER = ";"
DEFAULT_DUCKDB_PATH = "data/warehouse.duckdb"
RAW_SCHEMA = "raw"

INFORME_DIARIO = "informe_diario"
CADASTRO_FUNDOS = "cadastro_fundos"
CADASTRO_CLASSES = "cadastro_classes"
RAW_TABLES = (INFORME_DIARIO, CADASTRO_FUNDOS, CADASTRO_CLASSES)

# Members of registro_fundo_classe.zip (CVM Resolution 175 registry) -> raw table.
REGISTRO_MEMBERS = {
    "registro_fundo.csv": CADASTRO_FUNDOS,
    "registro_classe.csv": CADASTRO_CLASSES,
}

# Daily report columns renamed by CVM after Resolution 175 (old name -> current name), so
# that older reference months land in the same raw columns.
INFORME_COLUMN_RENAMES = {
    "CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE",
    "TP_FUNDO": "TP_FUNDO_CLASSE",
}

SOURCES = ("cvm", "p1-parquet")
_COMPETENCIA_RE = re.compile(r"^(\d{4})-(\d{2})$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------


def parse_competencia(value: str) -> tuple[int, int]:
    """Validate a reference month (``COMPETENCIA``) in ``YYYY-MM`` format."""
    match = _COMPETENCIA_RE.match(value)
    if not match:
        raise ValueError(f"invalid competencia {value!r}: expected YYYY-MM")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12 or year < 2000:
        raise ValueError(f"invalid competencia {value!r}: month 01-12 and year >= 2000")
    return year, month


def format_competencia(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def shift_competencia(competencia: str, months: int) -> str:
    year, month = parse_competencia(competencia)
    index = year * 12 + (month - 1) + months
    return format_competencia(index // 12, index % 12 + 1)


def previous_competencia(today: date) -> str:
    """Last complete reference month relative to ``today``."""
    return shift_competencia(format_competencia(today.year, today.month), -1)


def competencia_range(last: str, count: int) -> list[str]:
    """``count`` reference months ending at ``last``, oldest first."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return [shift_competencia(last, -offset) for offset in range(count - 1, -1, -1)]


def informe_diario_url(competencia: str, base_url: str = CVM_BASE_URL) -> str:
    year, month = parse_competencia(competencia)
    path = INFORME_DIARIO_PATH.format(yyyymm=f"{year:04d}{month:02d}")
    return f"{base_url.rstrip('/')}/{path}"


def registro_url(base_url: str = CVM_BASE_URL) -> str:
    return f"{base_url.rstrip('/')}/{REGISTRO_PATH}"


def normalize_informe_columns(columns: Iterable[str]) -> dict[str, str]:
    """Map each daily report column to its current (post Resolution 175) name."""
    return {column: INFORME_COLUMN_RENAMES.get(column.upper(), column) for column in columns}


def quote_identifier(name: str) -> str:
    """Quote a column name coming from a file header for use in SQL."""
    return '"' + name.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def qualified(table: str) -> str:
    if not _IDENTIFIER_RE.match(table):
        raise ValueError(f"invalid table name {table!r}")
    return f"{RAW_SCHEMA}.{table}"


@dataclass(frozen=True)
class LoadConfig:
    source: str
    competencias: tuple[str, ...]
    duckdb_path: Path
    path: Path | None
    base_url: str
    timeout: float
    retries: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="direct_load",
        description="Load CVM fund data into the DuckDB raw schema (RF-01, R-P3-01).",
    )
    parser.add_argument(
        "--competencia",
        help="last reference month to load, YYYY-MM (default: previous month for 'cvm'; "
        "all months found for 'p1-parquet')",
    )
    parser.add_argument(
        "--competencias", type=int, default=1, help="number of months ending at --competencia"
    )
    parser.add_argument(
        "--duckdb",
        default=os.environ.get("DUCKDB_PATH", DEFAULT_DUCKDB_PATH),
        help="DuckDB file (default: $DUCKDB_PATH or %(default)s)",
    )
    parser.add_argument("--source", choices=SOURCES, default="cvm")
    parser.add_argument("--path", help="base directory of the P1 Parquet (for p1-parquet)")
    parser.add_argument("--base-url", default=CVM_BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="HTTP attempts per file")
    return parser


def parse_args(argv: Sequence[str] | None = None, today: date | None = None) -> LoadConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.competencias < 1:
        parser.error("--competencias must be >= 1")
    if args.retries < 1:
        parser.error("--retries must be >= 1")
    if args.source == "p1-parquet" and not args.path:
        parser.error("--path is required with --source p1-parquet")

    competencias: tuple[str, ...] = ()
    last: str | None = args.competencia
    if last is None and args.source == "cvm":
        last = previous_competencia(today or datetime.now(UTC).date())
    if last is not None:
        try:
            competencias = tuple(competencia_range(last, args.competencias))
        except ValueError as exc:
            parser.error(str(exc))

    return LoadConfig(
        source=args.source,
        competencias=competencias,
        duckdb_path=Path(args.duckdb),
        path=Path(args.path) if args.path else None,
        base_url=args.base_url,
        timeout=args.timeout,
        retries=args.retries,
    )


# --------------------------------------------------------------------------------------
# I/O: download and transcoding
# --------------------------------------------------------------------------------------


def download(
    url: str,
    dest: Path,
    timeout: float = 120.0,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Download ``url`` to ``dest`` with a timeout and exponential-backoff retries."""
    request = urllib.request.Request(url, headers={"User-Agent": "dbt-dw-api/0.1 (RF-01)"})
    for attempt in range(1, retries + 1):
        try:
            with (
                urllib.request.urlopen(request, timeout=timeout) as response,
                dest.open("wb") as out,
            ):
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            logger.info("downloaded %s (%d bytes)", url, dest.stat().st_size)
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or attempt == retries:
                raise
            logger.warning("attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == retries:
                raise
            logger.warning("attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
        sleep(backoff ** (attempt - 1))
    raise RuntimeError("unreachable")  # pragma: no cover


def extract_csv_utf8(zip_path: Path, member: str, dest: Path, encoding: str = CVM_ENCODING) -> Path:
    """Extract one CSV member of a zip, transcoding it to UTF-8.

    Transcoding in Python is lenient with stray bytes (e.g. 0x83 in some CVM files) that
    DuckDB's own latin-1 decoder rejects.
    """
    with zipfile.ZipFile(zip_path) as archive, archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding=encoding, newline="")
        with dest.open("w", encoding="utf-8", newline="") as out:
            while chunk := text.read(1 << 20):
                out.write(chunk)
    return dest


def local_member_name(member: str) -> str:
    """File name used to extract a zip member into the work folder.

    Only the last path component is kept, so a member such as ``../x.csv`` or ``/tmp/x.csv``
    cannot write outside the folder (zip slip).
    """
    name = PurePosixPath(member.replace("\\", "/")).name
    if name in ("", ".", "..") or ":" in name:
        raise ValueError(f"unsafe zip member name {member!r}")
    return name


def single_csv_member(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(members) != 1:
        raise ValueError(f"expected one CSV in {zip_path.name}, found {members}")
    return members[0]


# --------------------------------------------------------------------------------------
# I/O: DuckDB writes
# --------------------------------------------------------------------------------------


def _read_csv_sql(csv_path: Path) -> str:
    return (
        f"read_csv({sql_literal(csv_path.as_posix())}, delim={sql_literal(CSV_DELIMITER)}, "
        "header=true, all_varchar=true, quote='\"')"
    )


def _columns(con: duckdb.DuckDBPyConnection, relation_sql: str) -> list[str]:
    return [str(row[0]) for row in con.execute(f"DESCRIBE SELECT * FROM {relation_sql}").fetchall()]


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [RAW_SCHEMA, table],
    ).fetchone()
    return bool(row and row[0])


def _stage_select(
    columns: dict[str, str], relation_sql: str, extra: dict[str, str], cast_varchar: bool
) -> str:
    projections = []
    for source_name, target_name in columns.items():
        expr = quote_identifier(source_name)
        if cast_varchar:
            expr = f"CAST({expr} AS VARCHAR)"
        projections.append(f"{expr} AS {quote_identifier(target_name)}")
    projections += [f"{expr} AS {name}" for name, expr in extra.items()]
    return f"SELECT {', '.join(projections)} FROM {relation_sql}"


def _upsert_partitions(
    con: duckdb.DuckDBPyConnection, table: str, stage_sql: str, partition_column: str
) -> None:
    """Replace the partitions (reference months) present in ``stage_sql`` -- idempotent."""
    target = qualified(table)
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE _stage AS {stage_sql}")
        if not _table_exists(con, table):
            con.execute(f"CREATE TABLE {target} AS SELECT * FROM _stage")
        else:
            existing = {c.lower() for c in _columns(con, target)}
            for column in _columns(con, "_stage"):
                if column.lower() not in existing:  # schema drift: new source column
                    con.execute(
                        f"ALTER TABLE {target} ADD COLUMN {quote_identifier(column)} VARCHAR"
                    )
            con.execute(
                f"DELETE FROM {target} WHERE {partition_column} IN "
                f"(SELECT DISTINCT {partition_column} FROM _stage)"
            )
            con.execute(f"INSERT INTO {target} BY NAME SELECT * FROM _stage")
        con.execute("DROP TABLE _stage")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _replace_table(con: duckdb.DuckDBPyConnection, table: str, stage_sql: str) -> None:
    con.execute(f"CREATE OR REPLACE TABLE {qualified(table)} AS {stage_sql}")


def _metadata(source: str, source_file: str, loaded_at: datetime) -> dict[str, str]:
    return {
        "_source": sql_literal(source),
        "_source_file": sql_literal(source_file),
        "_loaded_at": f"CAST({sql_literal(loaded_at.isoformat(sep=' '))} AS TIMESTAMP)",
    }


def load_informe_diario_csv(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    competencia: str,
    loaded_at: datetime,
    source_file: str,
) -> None:
    parse_competencia(competencia)
    relation = _read_csv_sql(csv_path)
    columns = normalize_informe_columns(_columns(con, relation))
    extra = {"competencia": sql_literal(competencia), **_metadata("cvm", source_file, loaded_at)}
    _upsert_partitions(
        con, INFORME_DIARIO, _stage_select(columns, relation, extra, False), "competencia"
    )


def load_cadastro_csv(
    con: duckdb.DuckDBPyConnection,
    table: str,
    csv_path: Path,
    loaded_at: datetime,
    source_file: str,
) -> None:
    relation = _read_csv_sql(csv_path)
    columns = {c: c for c in _columns(con, relation)}
    stage = _stage_select(columns, relation, _metadata("cvm", source_file, loaded_at), False)
    _replace_table(con, table, stage)


def _read_parquet_sql(glob: str) -> str:
    return f"read_parquet({sql_literal(glob)}, hive_partitioning=true, union_by_name=true)"


def load_informe_diario_parquet(
    con: duckdb.DuckDBPyConnection,
    base: Path,
    competencias: Sequence[str],
    loaded_at: datetime,
) -> None:
    glob = (base / INFORME_DIARIO / "**" / "*.parquet").as_posix()
    relation = _read_parquet_sql(glob)
    raw_columns = _columns(con, relation)
    columns = normalize_informe_columns(c for c in raw_columns if c.lower() != "competencia")
    if any(c.lower() == "competencia" for c in raw_columns):
        competencia_expr = 'CAST("competencia" AS VARCHAR)'
    else:
        competencia_expr = "strftime(CAST(\"DT_COMPTC\" AS DATE), '%Y-%m')"
    if competencias:
        months = ", ".join(sql_literal(c) for c in competencias)
        relation = f"(SELECT * FROM {relation} WHERE {competencia_expr} IN ({months}))"
    extra = {"competencia": competencia_expr, **_metadata("p1-parquet", glob, loaded_at)}
    _upsert_partitions(
        con, INFORME_DIARIO, _stage_select(columns, relation, extra, True), "competencia"
    )


def load_cadastro_parquet(
    con: duckdb.DuckDBPyConnection, table: str, base: Path, loaded_at: datetime
) -> None:
    glob = (base / table / "**" / "*.parquet").as_posix()
    relation = _read_parquet_sql(glob)
    columns = {c: c for c in _columns(con, relation)}
    stage = _stage_select(columns, relation, _metadata("p1-parquet", glob, loaded_at), True)
    _replace_table(con, table, stage)


def row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in RAW_TABLES:
        if _table_exists(con, table):
            row = con.execute(f"SELECT count(*) FROM {qualified(table)}").fetchone()
            counts[table] = int(row[0]) if row else 0
    return counts


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------


def load_from_cvm(con: duckdb.DuckDBPyConnection, config: LoadConfig, loaded_at: datetime) -> None:
    with tempfile.TemporaryDirectory(prefix="cvm-") as tmp:
        workdir = Path(tmp)
        for competencia in config.competencias:
            url = informe_diario_url(competencia, config.base_url)
            zip_path = download(url, workdir / Path(url).name, config.timeout, config.retries)
            member = single_csv_member(zip_path)
            csv_path = extract_csv_utf8(zip_path, member, workdir / local_member_name(member))
            load_informe_diario_csv(con, csv_path, competencia, loaded_at, url)
            logger.info("loaded %s for competencia %s", INFORME_DIARIO, competencia)
            csv_path.unlink()
            zip_path.unlink()

        url = registro_url(config.base_url)
        zip_path = download(url, workdir / Path(url).name, config.timeout, config.retries)
        for member, table in REGISTRO_MEMBERS.items():
            csv_path = extract_csv_utf8(zip_path, member, workdir / local_member_name(member))
            load_cadastro_csv(con, table, csv_path, loaded_at, f"{url}#{member}")
            logger.info("loaded %s from %s", table, member)


def load_from_parquet(
    con: duckdb.DuckDBPyConnection, config: LoadConfig, loaded_at: datetime
) -> None:
    if config.path is None:
        raise ValueError("path is required for p1-parquet")
    load_informe_diario_parquet(con, config.path, config.competencias, loaded_at)
    for table in (CADASTRO_FUNDOS, CADASTRO_CLASSES):
        load_cadastro_parquet(con, table, config.path, loaded_at)


def run(config: LoadConfig, now: datetime | None = None) -> dict[str, int]:
    """Load the configured source into DuckDB and return the row count per raw table."""
    # Naive UTC timestamp: dbt source freshness treats naive timestamps as UTC.
    loaded_at = (now or datetime.now(UTC)).astimezone(UTC).replace(tzinfo=None)
    config.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(config.duckdb_path)) as con:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
        if config.source == "cvm":
            load_from_cvm(con, config, loaded_at)
        else:
            load_from_parquet(con, config, loaded_at)
        return row_counts(con)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = parse_args(argv)
    logger.info(
        "source=%s competencias=%s duckdb=%s",
        config.source,
        ",".join(config.competencias) or "all",
        config.duckdb_path,
    )
    counts = run(config)
    for table, count in counts.items():
        print(f"row_count {RAW_SCHEMA}.{table} {count}")
    return 0
