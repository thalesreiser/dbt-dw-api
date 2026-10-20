"""FastAPI application (RNF-03): read-only over the DuckDB marts.

Run with `uvicorn fundos_api.main:app` (or `make api`).
"""

import logging
from datetime import date

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
    return app


app = create_app()
