"""Read-only connection to the warehouse (RNF-03, ADR 004)."""

from pathlib import Path
from typing import Annotated

import duckdb
import pytest
from conftest import api_client
from fastapi import Depends
from fastapi.testclient import TestClient

from fundos_api.config import Settings
from fundos_api.db import WarehouseUnavailableError, connect_read_only, get_connection
from fundos_api.main import create_app


@pytest.mark.parametrize(
    "statement",
    [
        "create table marts.x (a integer)",
        "insert into marts.fct_captacao_mensal (cnpj_fundo_classe) values ('11222333000181')",
        "delete from marts.dim_fundo",
        "drop table marts.dim_fundo",
    ],
)
def test_connection_rejects_writes(warehouse: Path, statement: str) -> None:
    with connect_read_only(warehouse) as con, pytest.raises(duckdb.Error, match="read-only"):
        con.execute(statement)


def test_missing_file_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.duckdb"
    with pytest.raises(WarehouseUnavailableError) as info:
        connect_read_only(path)
    assert str(tmp_path) not in str(info.value)
    assert not path.exists()


def test_unreadable_file_raises_clean_error(tmp_path: Path) -> None:
    path = tmp_path / "garbage.duckdb"
    path.write_bytes(b"x" * 4096)
    with pytest.raises(WarehouseUnavailableError, match="cannot be opened"):
        connect_read_only(path)


def _app_with_probe(settings: Settings) -> TestClient:
    """App plus a test-only route that tries to write through the app's connection."""
    app = create_app(settings)
    seen: list[duckdb.DuckDBPyConnection] = []

    @app.get("/_probe")
    def probe(
        con: Annotated[duckdb.DuckDBPyConnection, Depends(get_connection)],
    ) -> dict[str, str]:
        seen.append(con)
        try:
            con.execute("create table marts.intruder (a integer)")
        except duckdb.Error as exc:
            return {"write": "rejected", "error": type(exc).__name__}
        return {"write": "accepted"}

    app.state.seen = seen
    return api_client(app)


def test_write_through_app_connection_is_rejected_and_closed(settings: Settings) -> None:
    client = _app_with_probe(settings)
    response = client.get("/_probe")
    assert response.status_code == 200
    assert response.json()["write"] == "rejected"
    (con,) = client.app.state.seen  # type: ignore[attr-defined]
    with pytest.raises(duckdb.ConnectionException):
        con.execute("select 1")  # closed after the request


def test_dependency_missing_file_is_503(tmp_path: Path) -> None:
    settings = Settings(duckdb_path=tmp_path / "missing.duckdb", _env_file=None)  # type: ignore[call-arg]
    response = _app_with_probe(settings).get("/_probe")
    assert response.status_code == 503
    assert response.json() == {"detail": "warehouse unavailable"}
    assert not (tmp_path / "missing.duckdb").exists()
