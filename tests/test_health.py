"""`/health`: warehouse probe in read-only mode, 503 without exposing paths (RNF-03)."""

from pathlib import Path

from conftest import api_client, build_warehouse
from fastapi.testclient import TestClient

from fundos_api.config import Settings
from fundos_api.main import create_app


def _settings(path: Path) -> Settings:
    return Settings(duckdb_path=path, _env_file=None)  # type: ignore[call-arg]


def test_health_ok_reports_latest_month(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "reachable",
        "latest_month": "2026-09-01",
    }


def test_health_empty_fact_has_no_latest_month(tmp_path: Path) -> None:
    path = build_warehouse(tmp_path / "empty.duckdb", with_rows=False)
    response = api_client(create_app(_settings(path))).get("/health")
    assert response.status_code == 200
    assert response.json()["latest_month"] is None


def test_health_missing_file_is_503_and_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "missing.duckdb"
    response = api_client(create_app(_settings(path))).get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unreachable",
        "latest_month": None,
    }
    assert str(tmp_path) not in response.text
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_health_without_marts_is_503(tmp_path: Path) -> None:
    import duckdb

    path = tmp_path / "no_marts.duckdb"
    duckdb.connect(str(path)).close()
    response = api_client(create_app(_settings(path))).get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "reachable"
    assert response.json()["status"] == "unavailable"


def test_health_not_a_database_is_503(tmp_path: Path) -> None:
    path = tmp_path / "garbage.duckdb"
    path.write_bytes(b"not a duckdb file" * 100)
    response = api_client(create_app(_settings(path))).get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"


def test_openapi_documents_health(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert set(spec["paths"]["/health"]["get"]["responses"]) >= {"200", "503"}


def test_module_app_uses_process_settings() -> None:
    from fundos_api.main import app

    assert isinstance(app.state.settings, Settings)
