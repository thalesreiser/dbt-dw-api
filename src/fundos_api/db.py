"""Read-only access to the DuckDB warehouse (RNF-03, ADR 004).

Every request opens its own read-only connection and closes it when the response is done, so
the API never writes to the warehouse, never creates the file and does not keep it locked
between requests (dbt can rebuild it while the API is idle).
"""

from collections.abc import Iterator
from pathlib import Path

import duckdb
from fastapi import Request

from fundos_api.config import Settings


class WarehouseUnavailableError(Exception):
    """The warehouse file is missing or cannot be opened. The message never contains the path."""


def connect_read_only(path: Path) -> duckdb.DuckDBPyConnection:
    """Open the warehouse in read-only mode.

    The file must already exist: DuckDB would create an empty database on a plain connect, and
    a read-only connect to a missing file fails, but checking first gives a clear error.
    """
    if not path.is_file():
        raise WarehouseUnavailableError("warehouse file not found")
    try:
        return duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        raise WarehouseUnavailableError("warehouse cannot be opened") from exc


def get_settings_from_app(request: Request) -> Settings:
    """Settings the app was created with."""
    settings: Settings = request.app.state.settings
    return settings


def get_connection(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """FastAPI dependency: one read-only connection per request, always closed."""
    con = connect_read_only(get_settings_from_app(request).duckdb_path)
    try:
        yield con
    finally:
        con.close()
