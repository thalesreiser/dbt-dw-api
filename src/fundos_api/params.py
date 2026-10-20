"""Validated request inputs shared by the `/v1` endpoints (RNF-03).

Invalid input is rejected with 422 before any query runs. Unknown query parameters are
ignored (FastAPI default), so pagination combines freely with the filters of each endpoint.
"""

from typing import Annotated

from fastapi import Depends, Path, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict

from fundos_api.config import HARD_MAX_PAGE_SIZE, Settings
from fundos_api.db import get_settings_from_app

CNPJ_PATTERN = r"^\d{14}$"
MAX_OFFSET = 1_000_000

# A fund/class CNPJ in a path: exactly 14 digits, no punctuation.
CnpjPath = Annotated[
    str,
    Path(pattern=CNPJ_PATTERN, description="CNPJ with 14 digits, no punctuation."),
]


class PageParams(BaseModel):
    """Resolved pagination: `limit` defaulted and capped by the settings."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int


def pagination(
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=HARD_MAX_PAGE_SIZE,
            description="Page size; default `DEFAULT_PAGE_SIZE`, at most `MAX_PAGE_SIZE`.",
        ),
    ] = None,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET, description="Number of rows to skip.")] = 0,
) -> PageParams:
    """FastAPI dependency: validated pagination within `max_page_size`.

    Plain query parameters (not a query model), so it combines with any endpoint filters.
    Unknown query parameters are ignored, as everywhere in the API; invalid `limit`/`offset`
    values give 422.
    """
    size = settings.default_page_size if limit is None else limit
    if size > settings.max_page_size:
        raise RequestValidationError(
            [
                {
                    "type": "less_than_equal",
                    "loc": ("query", "limit"),
                    "msg": f"Input should be less than or equal to {settings.max_page_size}",
                    "input": size,
                    "ctx": {"le": settings.max_page_size},
                }
            ]
        )
    return PageParams(limit=size, offset=offset)
