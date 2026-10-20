"""API settings (RNF-03), read from the environment or a `.env` file with pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Upper bound for any configured page size, so a misconfiguration cannot open unbounded scans.
HARD_MAX_PAGE_SIZE = 1000


class Settings(BaseSettings):
    """Runtime configuration. Environment variables use the field name in upper case."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    duckdb_path: Path = Field(
        default=Path("data/warehouse.duckdb"),
        description="DuckDB warehouse file; opened read-only and never created by the API.",
    )
    marts_schema: str = Field(
        default="marts",
        pattern=r"^[a-z_][a-z0-9_]*$",
        description="Schema of the dbt marts the API reads.",
    )
    api_prefix: str = Field(default="/v1", pattern=r"^/[a-z0-9]+$")
    default_page_size: int = Field(default=50, ge=1, le=HARD_MAX_PAGE_SIZE)
    max_page_size: int = Field(default=500, ge=1, le=HARD_MAX_PAGE_SIZE)
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Key required in the `X-API-Key` header on every route under `api_prefix` (RF-10). "
            "When unset or blank those routes fail closed with 503."
        ),
    )
    rate_limit_requests: int = Field(
        default=60, ge=1, description="Requests allowed per key in each rate-limit window."
    )
    rate_limit_window_seconds: int = Field(
        default=60, ge=1, le=86_400, description="Length of the fixed rate-limit window."
    )

    @field_validator("api_key", mode="after")
    @classmethod
    def _blank_key_is_unset(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        return value

    @model_validator(mode="after")
    def _check_page_sizes(self) -> Self:
        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size must not exceed max_page_size")
        return self


@lru_cache
def get_settings() -> Settings:
    """Settings of the running process (cached; tests pass their own to `create_app`)."""
    return Settings()
