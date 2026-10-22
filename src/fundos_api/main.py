"""FastAPI application (RNF-03): read-only over the DuckDB marts.

Run with `uvicorn fundos_api.main:app` (or `make api`).
"""

import logging
from datetime import date
from typing import Any

import duckdb
from fastapi import FastAPI, Request, Response, Security, status
from fastapi.responses import JSONResponse

from fundos_api import __version__
from fundos_api.config import Settings, get_settings
from fundos_api.db import WarehouseUnavailableError, connect_read_only, get_settings_from_app
from fundos_api.routers import fundos, rankings, serie
from fundos_api.schemas import ErrorResponse, HealthResponse
from fundos_api.security import AUTH_RESPONSES, RateLimiter, require_api_key

logger = logging.getLogger(__name__)


def latest_month(con: duckdb.DuckDBPyConnection, schema: str) -> date | None:
    """Latest reference month loaded in the daily fact, or None when it is empty."""
    row = con.execute(f"select max(dt_mes_competencia) from {schema}.fct_informe_diario").fetchone()
    value = row[0] if row else None
    return value if isinstance(value, date) else None


def _warehouse_unavailable(request: Request, exc: Exception) -> JSONResponse:
    body = ErrorResponse(detail="warehouse unavailable")
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump())


def _with_max_page_size(app: FastAPI, max_page_size: int) -> None:
    """Document the configured `MAX_PAGE_SIZE` as the `limit` maximum in the OpenAPI (RF-11).

    The `Query` bound is the static `HARD_MAX_PAGE_SIZE`; the effective cap is a setting, so
    the generated document is patched once, when first built, to match what is enforced.
    """
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        document = build()
        for path_item in document.get("paths", {}).values():
            for operation in path_item.values():
                for param in operation.get("parameters", []):
                    if param.get("in") != "query" or param.get("name") != "limit":
                        continue
                    for option in [param["schema"], *param["schema"].get("anyOf", [])]:
                        if "maximum" in option:
                            option["maximum"] = max_page_size
        return document

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory; tests pass their own settings (e.g. a synthetic warehouse).

    `/health`, `/docs` and `/openapi.json` are public; every route under `api_prefix` requires
    the `X-API-Key` header and is rate limited per key (RF-10, `fundos_api.security`).
    """
    app = FastAPI(title="Fundos DW API", version=__version__)
    app.state.settings = config = settings or get_settings()
    app.state.rate_limiter = RateLimiter(
        config.rate_limit_requests, config.rate_limit_window_seconds
    )
    app.add_exception_handler(WarehouseUnavailableError, _warehouse_unavailable)

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse, "description": "Warehouse unavailable"}},
        tags=["meta"],
    )
    def health(request: Request, response: Response) -> HealthResponse:
        """Liveness plus a read-only probe of the warehouse; 503 when it cannot be read."""
        cfg = get_settings_from_app(request)
        try:
            with connect_read_only(cfg.duckdb_path) as con:
                month = latest_month(con, cfg.marts_schema)
        except WarehouseUnavailableError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="unavailable", database="unreachable")
        except duckdb.Error as exc:
            logger.warning("health check query failed: %s", type(exc).__name__)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="unavailable", database="reachable")
        return HealthResponse(status="ok", database="reachable", latest_month=month)

    for module in (fundos, serie, rankings):
        app.include_router(
            module.router,
            prefix=config.api_prefix,
            dependencies=[Security(require_api_key)],
            responses=AUTH_RESPONSES,
        )
    _with_max_page_size(app, config.max_page_size)
    return app


app = create_app()
