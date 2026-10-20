"""RF-10: `X-API-Key` on every `/v1/*` route (401), per-key rate limit (429), fail closed (503)."""

from pathlib import Path

import pytest
from conftest import TEST_API_KEY, api_client
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fundos_api.config import Settings
from fundos_api.main import create_app
from fundos_api.security import RateLimiter

PROTECTED = ["/v1/fundos", "/v1/fundos/11222333000181/serie", "/v1/rankings/captacao"]


def _client(
    settings: Settings, api_key: str | None = TEST_API_KEY, **overrides: object
) -> TestClient:
    return api_client(create_app(settings.model_copy(update=overrides)), api_key=api_key)


@pytest.mark.parametrize("url", PROTECTED)
def test_missing_key_is_401(settings: Settings, url: str) -> None:
    response = _client(settings, api_key=None).get(url)
    assert response.status_code == 401
    assert response.json() == {"detail": "missing X-API-Key header"}
    assert response.headers["WWW-Authenticate"] == "X-API-Key"


@pytest.mark.parametrize(
    "key", ["wrong", TEST_API_KEY + "x", TEST_API_KEY.upper(), TEST_API_KEY[:-1]]
)
def test_invalid_key_is_401_without_echoing_it(settings: Settings, key: str) -> None:
    response = _client(settings, api_key=key).get("/v1/fundos")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid API key"}
    assert TEST_API_KEY not in response.text


@pytest.mark.parametrize("url", PROTECTED)
def test_valid_key_is_200(client: TestClient, url: str) -> None:
    assert client.get(url).status_code == 200


def test_key_is_read_from_environment(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "from-env")
    loaded = Settings(duckdb_path=settings.duckdb_path, _env_file=None)  # type: ignore[call-arg]
    assert loaded.api_key == SecretStr("from-env")
    assert "from-env" not in repr(loaded)
    assert api_client(create_app(loaded), api_key="from-env").get("/v1/fundos").status_code == 200


def test_key_is_read_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY")
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=from-dotenv\nRATE_LIMIT_REQUESTS=7\n", encoding="utf-8")
    loaded = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert loaded.api_key == SecretStr("from-dotenv")
    assert loaded.rate_limit_requests == 7


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unconfigured_key_fails_closed(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("API_KEY")
    else:
        monkeypatch.setenv("API_KEY", value)
    unset = Settings(duckdb_path=settings.duckdb_path, _env_file=None)  # type: ignore[call-arg]
    assert unset.api_key is None
    for key in (None, "", "anything"):
        response = api_client(create_app(unset), api_key=key).get("/v1/fundos")
        assert response.status_code == 503
        assert response.json() == {"detail": "API key not configured on the server"}


@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json"])
def test_public_routes_need_no_key(settings: Settings, path: str) -> None:
    assert _client(settings, api_key=None).get(path).status_code == 200


def test_health_is_public_even_without_configured_key(settings: Settings) -> None:
    unset = settings.model_copy(update={"api_key": None})
    assert api_client(create_app(unset), api_key=None).get("/health").status_code == 200


def test_rate_limit_returns_429_with_retry_after(settings: Settings) -> None:
    client = _client(settings, rate_limit_requests=3, rate_limit_window_seconds=60)
    assert [client.get("/v1/fundos").status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.get("/v1/rankings/captacao")
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "rate limit exceeded"}
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    assert client.get("/health").status_code == 200


def test_rejected_requests_do_not_consume_the_limit(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"rate_limit_requests": 1}))
    for _ in range(5):
        assert api_client(app, api_key="wrong").get("/v1/fundos").status_code == 401
    assert api_client(app).get("/v1/fundos").status_code == 200


def test_limiter_window_resets() -> None:
    now = [100.0]
    limiter = RateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    now[0] = 103.2
    assert limiter.hit("k") == 7
    assert limiter.hit("other") is None
    now[0] = 109.9
    assert limiter.hit("k") == 1
    now[0] = 110.0
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    assert limiter.hit("k") == 10


def test_rate_limit_settings_are_validated() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_requests=0)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_window_seconds=0)  # type: ignore[call-arg]


def test_openapi_declares_api_key_scheme(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    scheme = spec["components"]["securitySchemes"]["ApiKeyAuth"]
    assert scheme == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": scheme["description"],
    }
    for path in ("/v1/fundos", "/v1/fundos/{cnpj}/serie", "/v1/rankings/captacao"):
        operation = spec["paths"][path]["get"]
        assert operation["security"] == [{"ApiKeyAuth": []}]
        assert {"401", "429", "503"} <= set(operation["responses"])
    assert "security" not in spec["paths"]["/health"]["get"]
